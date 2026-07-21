#!/usr/bin/env python3
"""
scope_guard.py — Hook PreToolUse (Claude Code) que aplica el alcance autorizado.

Barrera DETERMINISTA: inspecciona cada comando Bash antes de ejecutarlo, extrae los
targets (dominios, IPs, URLs) y los compara con contracts/scope.json. Bloquea cualquier
comando que apunte a un activo fuera de scope. No depende del criterio de ningún LLM.

Protocolo Claude Code:
- Recibe JSON por stdin: {"tool_name": "...", "tool_input": {"command": "..."}, ...}
- Para BLOQUEAR: imprime JSON de decisión y sale con código 0, o sale con código 2.
- Solo stdlib. Sin dependencias.
"""
import json
import sys
import os
import re
import ipaddress

SCOPE_CANDIDATES = [
    os.path.join("contracts", "scope.json"),
    os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "scope.json"),
]

# Hosts locales siempre permitidos (laboratorio del operador).
LOCAL_OK = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

# TLDs / sufijos que SÍ son un host de red (allowlist). Un token tipo `a.b.c` solo se considera
# target si su ÚLTIMA etiqueta está aquí. Así NO se confunden con dominios: ficheros
# (scope.json, scan.txt), código (json.load, os.path) ni scripts (run.sh) — esa confusión era
# justo la que bloqueaba en falso `cat contracts/scope.json` y tumbó el engagement. Se excluyen
# a propósito TLDs que chocan con extensiones/código comunes (sh, md, id, so, is, rs, py, js,
# zip...). Un dominio real con TLD exótico no listado no se gatea por nombre, pero queda el
# bloqueo explícito por out_of_scope y la aprobación humana por acción como segunda capa.
KNOWN_TLDS = {
    # gTLD clásicos + comunes
    "com", "net", "org", "edu", "gov", "mil", "int", "io", "co", "ai", "app", "dev", "xyz",
    "info", "biz", "online", "site", "tech", "store", "cloud", "host", "space", "live", "news",
    "blog", "shop", "work", "digital", "network", "systems", "tools", "email", "page", "pro",
    # ccTLD comunes
    "us", "uk", "es", "de", "fr", "it", "nl", "ru", "cn", "jp", "br", "ca", "au", "in", "mx",
    "ar", "cl", "pl", "se", "no", "fi", "dk", "ch", "at", "be", "pt", "gr", "cz", "ro", "hu",
    "ie", "nz", "za", "kr", "tw", "hk", "sg", "ae", "sa", "il", "tr", "ua", "my", "th", "vn",
    "ph", "eu", "me", "tv", "cc", "gg",
    # sufijos internos / laboratorios + TLD reservados de documentación (RFC 2606/6761)
    "local", "internal", "lan", "intranet", "corp", "home", "htb", "thm", "vulnhub", "dockerlabs",
    "lab", "example", "invalid",
}

DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.I)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
URL_RE = re.compile(r"https?://([^/\s:]+)", re.I)

# Metacaracteres de shell/plantilla que NUNCA aparecen en un hostname/IP real. Si un "host"
# capturado (p.ej. de una URL `https://$host/…` o `https://{target}/…`) los contiene, es una
# VARIABLE/PLACEHOLDER sin expandir, no un target verificable. No se puede comprobar su scope de
# forma determinista => se deniega (fail-closed) con un motivo accionable, en vez del confuso
# "Dominio {host} NO está en in_scope" que hacía perder turnos al subagente. Bloquear un placeholder
# es correcto: fuerza a lanzar una invocación por host LITERAL, que el guard sí puede verificar.
PLACEHOLDER_RE = re.compile(r"[\$\{\}\(\)`%<>\\!*]")


def _is_placeholder(token):
    """True si `token` contiene un metacarácter de shell/plantilla (variable/placeholder sin
    expandir): no es un host verificable."""
    return bool(PLACEHOLDER_RE.search(token))


def _is_target_domain(token):
    """True solo si `token` (algo tipo a.b.c) es un host de red real: su última etiqueta es un
    TLD/sufijo conocido. Filtra ficheros, rutas y código que el regex confunde con dominios."""
    return token.rsplit(".", 1)[-1].lower() in KNOWN_TLDS


def deny(reason: str):
    """Emite decisión de bloqueo en el formato de Claude Code y termina."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def load_scope():
    for path in SCOPE_CANDIDATES:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    # Sin scope definido => fail-closed: bloquea todo lo que parezca tocar un target.
    return None


def domain_in_list(host: str, patterns):
    host = host.lower().rstrip(".")
    for p in patterns:
        p = p.lower().rstrip(".")
        if p.startswith("*."):
            base = p[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == p:
            return True
    return False


def ip_in_scope(ip: str, ips, cidrs):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if ip in ips:
        return True
    for c in cidrs:
        try:
            if addr in ipaddress.ip_network(c, strict=False):
                return True
        except ValueError:
            continue
    return False


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # sin input parseable, no interferir

    if event.get("tool_name") != "Bash":
        sys.exit(0)

    command = (event.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    scope = load_scope()
    # Dominios que el operador puso en el scope (in + out): SIEMPRE son candidatos aunque su TLD
    # no esté en KNOWN_TLDS (p.ej. un `.test` interno), para no perder un out_of_scope explícito.
    scoped = []
    if scope:
        scoped = (scope.get("in_scope", {}).get("domains", []) +
                  scope.get("out_of_scope", {}).get("domains", []))

    # Recolecta candidatos a target del comando.
    hosts = set()
    for m in URL_RE.finditer(command):
        hosts.add(m.group(1))
    for m in DOMAIN_RE.finditer(command):
        tok = m.group(0)
        if _is_target_domain(tok) or domain_in_list(tok, scoped):
            hosts.add(tok)  # host de red real o dominio del scope; ficheros/código se ignoran
    ips = set(IP_RE.findall(command))

    targets = {h for h in hosts if h.lower() not in LOCAL_OK}
    targets |= {ip for ip in ips if ip not in LOCAL_OK}

    if not targets:
        sys.exit(0)  # comando sin target externo (ls, cat, etc.)

    if scope is None:
        deny("No existe contracts/scope.json. Define el alcance autorizado antes de "
             "lanzar comandos contra cualquier target (fail-closed).")

    # Placeholders/variables sin expandir ($host, {target}, ${T}…): no son verificables. Se deniega
    # con un motivo accionable ANTES del chequeo in/out, para que el subagente expanda a host literal
    # en vez de perder turnos creyendo que un host real quedó fuera de scope.
    placeholders = sorted(t for t in targets if _is_placeholder(t))
    if placeholders:
        deny(f"Target no verificable: «{placeholders[0]}» contiene una variable/placeholder de "
             f"shell sin expandir. scope_guard exige hostnames/IPs LITERALES para comprobar el "
             f"alcance de forma determinista. Expande la variable y lanza UNA invocación por host "
             f"literal (sin $var, {{}}, ni bucles con variable de host). Bloqueado por scope_guard "
             f"(fail-closed).")

    in_scope = scope.get("in_scope", {})
    out_scope = scope.get("out_of_scope", {})
    in_domains = in_scope.get("domains", [])
    in_ips = in_scope.get("ips", [])
    in_cidrs = in_scope.get("cidrs", [])
    in_urls_hosts = [URL_RE.match(u).group(1) for u in in_scope.get("urls", []) if URL_RE.match(u)]
    in_domains = in_domains + in_urls_hosts
    out_domains = out_scope.get("domains", [])
    out_ips = out_scope.get("ips", [])

    for t in sorted(targets):
        is_ip = bool(IP_RE.fullmatch(t))
        # 1) Bloqueo explícito por out_of_scope.
        if is_ip and t in out_ips:
            deny(f"Target {t} está EXPLÍCITAMENTE fuera de scope (out_of_scope.ips).")
        if not is_ip and domain_in_list(t, out_domains):
            deny(f"Target {t} está EXPLÍCITAMENTE fuera de scope (out_of_scope.domains).")
        # 2) Debe estar dentro de in_scope.
        if is_ip:
            if not ip_in_scope(t, in_ips, in_cidrs):
                deny(f"IP {t} NO está en in_scope. Comando bloqueado por scope_guard.")
        else:
            if not domain_in_list(t, in_domains):
                deny(f"Dominio {t} NO está en in_scope. Comando bloqueado por scope_guard.")

    sys.exit(0)  # todos los targets en scope => permitir


if __name__ == "__main__":
    main()
