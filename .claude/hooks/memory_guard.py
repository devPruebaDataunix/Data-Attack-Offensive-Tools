#!/usr/bin/env python3
"""
memory_guard.py — Hook PreToolUse que SANEA la memoria de aprendizaje por agente (la pieza que
hace de "sin datos de cliente en memoria" una GARANTÍA de código, no una promesa de prompt).

Cuando un agente con `memory:` escribe en su directorio de memoria persistente, este hook inspecciona
el contenido ANTES de que toque disco y BLOQUEA la escritura si contiene datos que jamás deben
persistir entre engagements: secretos, identificadores del scope (IPs/dominios del cliente), IPs
enrutables o loot crudo (hashes). La memoria solo debe acumular TÉCNICA generalizada.

Por qué es crítico (CONSTITUTION §1, aislamiento de cliente / OWASP LLM02):
- `memory: project` -> `.claude/agent-memory/<agente>/` se **comparte por git**: en un repo público, un
  identificador de cliente ahí filtraría entre clientes y al mundo.
- `memory: local`   -> `.claude/agent-memory-local/<agente>/` es per-operador: filtraría entre los
  clientes de ese operador.
Cubrimos AMBAS (prefijo `.claude/agent-memory`).

Protocolo Claude Code (igual que scope_guard.py):
- Recibe JSON por stdin: {"tool_name","tool_input":{...}}.
- Para BLOQUEAR: imprime la decisión PreToolUse (permissionDecision=deny) y sale 0.
- Cualquier ambigüedad (no es Write/Edit, no es un fichero de memoria, error) => sale 0 (fail-open:
  un guard nunca debe romper el flujo; el bloqueo solo ocurre ante una violación clara).

Solo stdlib + módulos del repo (redactor, scope_guard). Sin dependencias externas.
"""
import ipaddress
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
# Prefijo que cubre tanto `.claude/agent-memory/` (project) como `.claude/agent-memory-local/` (local).
MEMORY_PREFIX = os.path.join(ROOT, ".claude", "agent-memory")

# Reutilizamos los detectores ya existentes en el repo (DRY): secretos -> redactor; scope -> scope_guard.
# Ambos módulos solo ejecutan su main() bajo `if __name__ == "__main__"`, así que importarlos no tiene
# efectos secundarios.
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HOOKS_DIR)
try:
    from redactor import scan as scan_secrets
except Exception:  # noqa: BLE001 — sin detector de secretos, el resto de comprobaciones siguen
    scan_secrets = None
try:
    from scope_guard import load_scope, domain_in_list, ip_in_scope, IP_RE, DOMAIN_RE, _is_target_domain
except Exception:  # noqa: BLE001 — sin scope_guard, caemos a regex locales mínimas
    load_scope = None
    IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.I)

    def domain_in_list(host, patterns):  # type: ignore  # fallback mínimo
        host = host.lower().rstrip(".")
        return any(host == p.lower().rstrip(".") for p in patterns)

    def ip_in_scope(ip, ips, cidrs):  # type: ignore
        return ip in (ips or [])

    def _is_target_domain(token):  # type: ignore
        return True

# Loot crudo de alta señal (deliberadamente conservador para FP ~0). Una técnica generalizada nunca
# necesita el hash real de un objetivo.
LOOT_PATTERNS = [
    ("unix_hash",  re.compile(r"(?m)^[^\s:]{1,64}:\$[0-9a-z]{1,2}\$[./A-Za-z0-9]{8,}")),  # user:$6$... (/etc/shadow)
    ("ntlm_pair",  re.compile(r"\b[a-fA-F0-9]{32}:[a-fA-F0-9]{32}\b")),                    # LM:NT (secretsdump)
]

# Referencia `file:line` de código fuente (white-box, code-recon). Una técnica generalizada NUNCA
# necesita un `src/db/user.ts:42` concreto — eso es un identificador del código del cliente (zona E3)
# que filtraría entre clientes del operador. Se exige la forma `<ruta>.<ext>:<línea>` (con `:línea`)
# para FP ~0: un nombre de fichero suelto sin línea no dispara; la técnica debe usar `<handler>`.
CODE_REF_RE = re.compile(
    r"(?<![\w])[\w./\\-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|java|rb|php|cs|rs|c|cc|cpp|hpp|kt|swift|scala|pl|sh|sql):\d+",
    re.I)


def is_memory_path(file_path):
    """True si `file_path` cae bajo `.claude/agent-memory*/` (project o local)."""
    if not file_path:
        return False
    try:
        rp = os.path.realpath(file_path)
    except Exception:  # noqa: BLE001
        return False
    prefix = os.path.realpath(MEMORY_PREFIX)
    return rp == prefix or rp.startswith(prefix + os.sep) or rp.startswith(prefix)


def extract_new_text(tool_name, tool_input):
    """Texto que el agente intenta ESCRIBIR (solo contenido nuevo; old_string no nos interesa)."""
    ti = tool_input or {}
    if tool_name == "Write":
        return ti.get("content", "") or ""
    if tool_name == "Edit":
        return ti.get("new_string", "") or ""
    if tool_name == "MultiEdit":
        return "\n".join((e or {}).get("new_string", "") or "" for e in (ti.get("edits") or []))
    return ""


def find_violations(text, scope):
    """Devuelve la lista de violaciones (cadenas legibles). Vacía => la escritura es admisible.
    Determinista: secretos + identificadores del scope + IPs enrutables + loot."""
    violations = []
    if not text:
        return violations

    # 1) Secretos (operador + proveedor + genéricos). En memoria NO debe persistir ninguno.
    if scan_secrets is not None:
        for label in scan_secrets(text, operator_only=False):
            violations.append(f"secreto:{label}")

    # 2) Identificadores del cliente declarados en el scope (IPs/CIDR/dominios, in y out).
    in_ips = in_cidrs = scoped_domains = []
    if scope:
        ins = scope.get("in_scope", {}) or {}
        out = scope.get("out_of_scope", {}) or {}
        in_ips = (ins.get("ips", []) or []) + (out.get("ips", []) or [])
        in_cidrs = ins.get("cidrs", []) or []
        scoped_domains = (ins.get("domains", []) or []) + (out.get("domains", []) or [])

    found_ips = set(IP_RE.findall(text))
    for ip in sorted(found_ips):
        if scope and ip_in_scope(ip, in_ips, in_cidrs):
            violations.append(f"ip_scope:{ip}")

    if scoped_domains:
        for tok in set(DOMAIN_RE.findall(text)):
            if domain_in_list(tok, scoped_domains):
                violations.append(f"dominio_scope:{tok}")

    # 3) IPs enrutables (públicas): una técnica generalizada no debe llevar un objetivo concreto.
    #    Se permiten privadas/loopback/documentación (aparecen en ejemplos).
    for ip in sorted(found_ips):
        try:
            if ipaddress.ip_address(ip).is_global:
                violations.append(f"ip_publica:{ip}")
        except ValueError:
            continue

    # 4) Loot crudo (hashes capturados).
    for label, rx in LOOT_PATTERNS:
        if rx.search(text):
            violations.append(f"loot:{label}")

    # 5) Referencias `file:line` del código del cliente (white-box). Identificador de E3, no técnica.
    for m in sorted(set(CODE_REF_RE.findall(text))):
        violations.append(f"code_ref:{m}")

    # Únicas y ordenadas, para un mensaje estable.
    return sorted(set(violations))


def deny(violations):
    """Emite la decisión de bloqueo PreToolUse de Claude Code y termina."""
    reason = (
        "memory_guard: la escritura a la memoria de aprendizaje contiene datos que NO pueden "
        "persistir entre engagements (aislamiento de cliente, CONSTITUTION §1): "
        + ", ".join(violations) + ". La memoria solo acumula TÉCNICA generalizada y sanitizada: "
        "quita el identificador/secreto/loot o sustitúyelo por un marcador genérico (p.ej. "
        "'<IP-del-objetivo>', 'el WAF', '[REDACTED]') y reescribe la lección sin datos crudos."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — sin input parseable, no interferir
        sys.exit(0)

    tool_name = event.get("tool_name")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    tool_input = event.get("tool_input") or {}
    if not is_memory_path(tool_input.get("file_path", "")):
        sys.exit(0)  # no es un fichero de memoria de agente => no nos incumbe

    text = extract_new_text(tool_name, tool_input)
    scope = load_scope() if load_scope else None
    violations = find_violations(text, scope)
    if violations:
        deny(violations)
    sys.exit(0)  # memoria limpia => permitir


if __name__ == "__main__":
    main()
