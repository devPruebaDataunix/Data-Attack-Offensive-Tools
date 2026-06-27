#!/usr/bin/env python3
"""
noise_guard.py — Hook PreToolUse: control determinista ANTI-ALBOROTO (control C18).

El escaneo ruidoso / sin proporción está DESCARTADO por defecto: tumba servicios, dispara
IDS/IPS y delata al pentester. Este hook BLOQUEA de forma determinista los comandos
inequívocamente ruidosos o DoS-adjacent (timing 'insane', floods sin límite de rate, fuerza
bruta con demasiados hilos, fuzzing web con cientos de hilos, rustscan con batch/ulimit sin
acotar). No sustituye al criterio del
agente (sigilo proporcional vive en el prompt y en el modelo de decisión del Orquestador): es
la red dura para que un agente —o un target que intente provocarlo— no genere alboroto.

Configuración (contracts/scope.json -> constraints):
- `allow_noisy` (bool, def. false): si la ROE autoriza ruido (p.ej. stress test), DESACTIVA este
  guard por completo. Es el único override.
- `stealth` (bool, def. false): endurece los umbrales (deniega también -T4/-A/-p- rápido y baja el
  cap de rate y de hilos).
- `max_scan_rate` (int, pps): cap de rate para masscan/zmap; si no está, DEFAULT_RATE_CAP.

Protocolo Claude Code (idéntico a budget_guard.py / scope_guard.py):
- Recibe JSON por stdin: {"tool_name":"Bash","tool_input":{"command":"..."}, ...}.
- Para BLOQUEAR: imprime la decisión `deny` y sale 0.
- Cualquier error => sale 0 (FAIL-OPEN: un guard nunca rompe el entorno por sí mismo).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCOPE = os.path.join(ROOT, "contracts", "scope.json")

DEFAULT_RATE_CAP = 1000      # pps para masscan/zmap si no hay constraints.max_scan_rate
THREAD_CAP = 16              # hilos de fuerza bruta (hydra/medusa: su -t es paralelismo real)
WEB_THREAD_CAP = 100         # hilos de fuzzing web (ffuf/feroxbuster/gobuster/wfuzz)
STEALTH_RATE_CAP = 100
STEALTH_THREAD_CAP = 8
STEALTH_WEB_THREAD_CAP = 40
RUSTSCAN_BATCH_CAP = 4500            # batch de rustscan (default ~4500); por encima = ruidoso
STEALTH_RUSTSCAN_BATCH_CAP = 1000
RUSTSCAN_ULIMIT_CAP = 10000          # --ulimit alto = muchos sockets en paralelo = ruidoso
STEALTH_RUSTSCAN_ULIMIT_CAP = 5000


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def constraints():
    try:
        with open(SCOPE, "r", encoding="utf-8") as f:
            return json.load(f).get("constraints", {}) or {}
    except Exception:
        return {}


def has(cmd, tool):
    """El ejecutable `tool` aparece como token de comando (inicio, tras separador shell, o tras una
    ruta: /usr/bin/nmap). NO es un parseo a prueba de adversario (la obfuscación deliberada lo evade);
    el modelo de amenaza es el agente que se desboca o el ruido accidental, no la evasión activa.
    El ejecutable debe ir seguido de espacio/fin/separador, para no confundir `masscan` dentro de
    una ruta o URL (p.ej. `wget http://x/masscan.tar.gz`) con una invocación de la herramienta."""
    return re.search(r"(?:^|[\s;|&(/\\])" + re.escape(tool) + r"(?=\s|$|[;|&])", cmd) is not None


def num_after(cmd, flag_re):
    m = re.search(flag_re, cmd)
    try:
        return int(m.group(1)) if m else None
    except (ValueError, IndexError):
        return None


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if event.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (event.get("tool_input", {}) or {}).get("command", "")
    if not cmd or not cmd.strip():
        sys.exit(0)

    c = constraints()
    if c.get("allow_noisy") is True:   # la ROE autoriza ruido explícitamente => guard off
        sys.exit(0)
    stealth = c.get("stealth") is True
    rate_cap = c.get("max_scan_rate") if isinstance(c.get("max_scan_rate"), int) else DEFAULT_RATE_CAP
    if stealth:
        rate_cap = min(rate_cap, STEALTH_RATE_CAP)
    thread_cap = STEALTH_THREAD_CAP if stealth else THREAD_CAP
    web_cap = STEALTH_WEB_THREAD_CAP if stealth else WEB_THREAD_CAP
    rs_batch_cap = STEALTH_RUSTSCAN_BATCH_CAP if stealth else RUSTSCAN_BATCH_CAP
    rs_ulimit_cap = STEALTH_RUSTSCAN_ULIMIT_CAP if stealth else RUSTSCAN_ULIMIT_CAP

    low = cmd.lower()
    fix = ("Reformula con sentido y bajo ruido (escaneo dirigido, rate limitado). Si la ROE "
           "autoriza ruido, ponlo explícito con constraints.allow_noisy=true en scope.json.")

    # --- nmap ---
    if has(low, "nmap"):
        if re.search(r"(?:^|\s)-t5\b", low):
            deny(f"ANTI-ALBOROTO (C18): nmap -T5 ('insane') es ruidoso y DoS-adjacent. Usa -T2/-T3. {fix}")
        mr = num_after(low, r"--min-rate[ =](\d+)")
        if mr is not None and mr > 5000:
            deny(f"ANTI-ALBOROTO (C18): nmap --min-rate {mr} es un flood. Bájalo (<=5000) o usa timing -T3. {fix}")
        if stealth:
            if re.search(r"(?:^|\s)-t4\b", low):
                deny(f"ANTI-ALBOROTO (C18, stealth): nmap -T4 es demasiado ruidoso en modo sigilo. Usa -T2/-T3. {fix}")
            if re.search(r"(?:^|\s)-a\b", low):
                deny(f"ANTI-ALBOROTO (C18, stealth): nmap -A (agresivo: OS+scripts+traceroute) delata. Enumera por fases. {fix}")
            if re.search(r"(?:^|\s)-p-\b", low) and re.search(r"-t[45]\b", low):
                deny(f"ANTI-ALBOROTO (C18, stealth): barrido full-range a timing alto es muy ruidoso. Acota puertos o baja el timing. {fix}")

    # --- masscan / zmap (floods de red) ---
    for tool in ("masscan", "zmap"):
        if has(low, tool):
            rate = num_after(low, r"--(?:max-)?rate[ =](\d+)")
            if rate is None:
                deny(f"ANTI-ALBOROTO (C18): {tool} sin --rate es un flood sin límite. Añade --rate <= {rate_cap}. {fix}")
            if rate > rate_cap:
                deny(f"ANTI-ALBOROTO (C18): {tool} --rate {rate} supera el cap de {rate_cap} pps. {fix}")

    # --- rustscan (descubrimiento full-range rápido; OK como front-end si acota el ritmo) ---
    if has(low, "rustscan"):
        b = num_after(low, r"(?:-b|--batch-size)[ =]?(\d+)")
        if b is not None and b > rs_batch_cap:
            deny(f"ANTI-ALBOROTO (C18): rustscan --batch-size {b} supera el cap de {rs_batch_cap}; "
                 f"bájalo y deja el -sV al nmap dirigido sobre los puertos abiertos. {fix}")
        ul = num_after(low, r"--ulimit[ =]?(\d+)")
        if ul is not None and ul > rs_ulimit_cap:
            deny(f"ANTI-ALBOROTO (C18): rustscan --ulimit {ul} (sockets en paralelo) supera {rs_ulimit_cap}. {fix}")
        if stealth and b is None:
            deny(f"ANTI-ALBOROTO (C18, stealth): en sigilo, rustscan debe acotar el ritmo explícitamente "
                 f"(-b <= {rs_batch_cap}). {fix}")

    # --- fuerza bruta de credenciales (ruido + lockout) ---
    # Solo hydra/medusa: su -t es paralelismo real. ncrack usa -T (timing) y patator otros flags;
    # incluirlos malinterpretaría el flag, así que quedan fuera de este check de hilos.
    for tool in ("hydra", "medusa"):
        if has(low, tool):
            th = num_after(low, r"-t[ =]?(\d+)") or num_after(low, r"--threads[ =](\d+)")
            if th is not None and th > thread_cap:
                deny(f"ANTI-ALBOROTO (C18): {tool} con {th} hilos es ruidoso y arriesga lockout. "
                     f"Limita a <= {thread_cap} y vigila la política de bloqueo. {fix}")

    # --- fuzzing web (flood del servidor) ---
    for tool in ("ffuf", "feroxbuster", "gobuster", "wfuzz"):
        if has(low, tool):
            th = num_after(low, r"-t[ =]?(\d+)") or num_after(low, r"--threads[ =](\d+)")
            if th is not None and th > web_cap:
                deny(f"ANTI-ALBOROTO (C18): {tool} con {th} hilos floodea el servidor. Limita a <= {web_cap}. {fix}")

    sys.exit(0)


if __name__ == "__main__":
    main()
