#!/usr/bin/env python3
"""
circuit_breaker.py — Hook determinista de CIRCUIT-BREAKER por target (control C22, OWASP LLM10
Unbounded Consumption + no-daño/§9). Idea reimplementada limpia de BugTraceAI (AGPL → solo ideas).

Corta el MACHAQUE de un target CAÍDO/inalcanzable. Cuenta fallos de CONEXIÓN consecutivos por host
(rechazo/timeout/DNS/host-down) — NO un 4xx/5xx, que significa que el host SÍ responde — y, al superar
un umbral, ABRE el breaker de ese host: los siguientes comandos contra él se BLOQUEAN hasta que pase un
cooldown (medio-abierto) o el host vuelva a responder (se cierra). Complementa C13 (kill-switch global),
C18 (anti-ruido) y C19 (anti-bucle de comando idéntico): aquí el eje es un TARGET que no responde.

Corre en DOS fases sobre Bash (registrado en PreToolUse y PostToolUse):
- PostToolUse: observa la salida del comando, clasifica (fail/up/neutral) y actualiza el estado por host.
- PreToolUse: si algún target del comando tiene el breaker ABIERTO y sin cooldown cumplido, BLOQUEA.

Estado en contracts/.circuit_state (gitignored), keyed por engagement_id (se reinicia al cambiar de
engagement, igual que budget_guard). Umbral/cooldown configurables en scope.constraints
(circuit_breaker_threshold, def. 5; circuit_breaker_cooldown_s, def. 300). Solo stdlib. FAIL-OPEN:
cualquier error del guard => no interfiere (jamás rompe el entorno por sí mismo).
"""
import json
import os
import re
import sys
import time

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
STATE_FILE = os.path.join(ROOT, "contracts", ".circuit_state")
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")
SCOPE = os.path.join(ROOT, "contracts", "scope.json")
DEFAULT_THRESHOLD = 5
DEFAULT_COOLDOWN_S = 300

# Señales de FALLO DE CONEXIÓN (host no alcanzable) que las herramientas emiten por STDERR
# (curl/ssh/nc/wget). Se buscan SOLO en stderr para que el BODY de una respuesta (stdout, que un
# target hostil controla) NO pueda DISPARAR el breaker devolviendo strings de error falsos
# (auto-evasión del pentest). Deliberadamente NO incluye 4xx/5xx: una respuesta HTTP demuestra que el
# host RESPONDE.
_FAIL_CONN_RE = re.compile(
    r"connection refused|connection timed out|connect timed out|failed to connect|"
    r"couldn'?t connect|could not connect|could not open connection|connect failed|"
    r"could not resolve host|name or service not known|"
    r"temporary failure in name resolution|no route to host|network is unreachable|"
    r"connection reset by peer|operation timed out|read timed out|timed out after|no response",
    re.I,
)
# Señales de host CAÍDO que emiten HERRAMIENTAS DE SCAN por su propia salida (nmap/ping). OJO: el hook
# no puede distinguir el stdout de nmap del BODY de un curl (ambos van a stdout); por eso estas frases
# SOLO cuentan como fallo cuando el COMANDO es un escáner (_SCAN_TOOL_RE), no un fetcher de contenido
# (curl/wget/nc), para que un target hostil no dispare el breaker metiéndolas en su respuesta.
_FAIL_TOOL_RE = re.compile(
    r"host seems down|0 hosts up|note: host seems down|destination host unreachable|100% packet loss",
    re.I,
)
_SCAN_TOOL_RE = re.compile(r"\b(?:nmap|ping|fping|hping3?|masscan|rustscan|arping|nping)\b", re.I)
# Señales de que el host SÍ responde (cierran/resetean el breaker): línea de estado HTTP, host up,
# puertos abiertos. Una respuesta = el host está vivo. Ganan sobre cualquier señal de fallo.
_UP_RE = re.compile(
    r"http/[12](?:\.[019])?\s+\d{3}|host is up|[1-9]\d*\s+hosts?\s+up|\d{1,5}/(?:tcp|udp)\s+open\b|"
    r"< http/|> http/|\bstatus:\s*\d{3}|\b(?:200|301|302|401|403|404)\b\s+(?:ok|found|moved|forbidden|unauthorized|not found)",
    re.I,
)


def classify(stderr_text, full_text=None, command=""):
    """'up' si hay señal de host-vivo (GANA); 'fail' si hay un fallo de CONEXIÓN en STDERR, o una frase
    de host-caído de una tool de scan EN EL TEXTO COMPLETO **cuando el comando es un escáner**; si no,
    'neutral'. Dos defensas contra la AUTO-EVASIÓN (que un target dispare su propio breaker con strings
    de error en su respuesta): (1) los fallos de conexión solo se leen de STDERR, no del body (stdout);
    (2) las frases tool-self (nmap/ping) solo cuentan si el COMANDO es un escáner que las emite por su
    salida —no un `curl`/`wget` cuyo stdout es un body atacante-controlado—. Puro y testeable."""
    full_text = full_text if full_text is not None else (stderr_text or "")
    stderr_text = stderr_text or ""
    if _UP_RE.search(full_text):
        return "up"
    tool_self = bool(_SCAN_TOOL_RE.search(command or "")) and bool(_FAIL_TOOL_RE.search(full_text))
    if _FAIL_CONN_RE.search(stderr_text) or tool_self:
        return "fail"
    return "neutral"


def _engagement_key():
    for p in (ENGAGEMENT, SCOPE):
        try:
            with open(p, encoding="utf-8") as f:
                eid = json.load(f).get("engagement_id")
            if eid:
                return str(eid)
        except Exception:
            continue
    return "default"


def _config():
    thr, cd = DEFAULT_THRESHOLD, DEFAULT_COOLDOWN_S
    try:
        with open(SCOPE, encoding="utf-8") as f:
            c = json.load(f).get("constraints", {}) or {}
        if isinstance(c.get("circuit_breaker_threshold"), int) and c["circuit_breaker_threshold"] > 0:
            thr = c["circuit_breaker_threshold"]
        if isinstance(c.get("circuit_breaker_cooldown_s"), int) and c["circuit_breaker_cooldown_s"] > 0:
            cd = c["circuit_breaker_cooldown_s"]
    except Exception:
        pass
    return thr, cd


def load_state(key):
    """Estado {host: {fails, opened_at}} para `key`. Si el fichero es de otro engagement, se reinicia."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        if st.get("key") == key and isinstance(st.get("targets"), dict):
            return st["targets"]
    except Exception:
        pass
    return {}


def save_state(key, targets):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "targets": targets}, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass  # si no se puede persistir, no rompemos nada


def open_breaker_target(targets_state, hosts, now, cooldown):
    """Primer host de `hosts` cuyo breaker está ABIERTO y con el cooldown SIN cumplir (=> bloquear).
    Si el cooldown ya pasó, se permite un sondeo (medio-abierto): no lo devuelve. Puro y testeable."""
    for h in sorted(hosts):
        rec = targets_state.get(h)
        if rec and rec.get("opened_at") and (now - rec["opened_at"]) < cooldown:
            return h, rec
    return None, None


def record_outcome(targets_state, hosts, verdict, now, threshold):
    """Actualiza el estado por host según el `verdict` ('fail'/'up'/'neutral'). Muta y devuelve el
    dict. 'fail' incrementa y abre al llegar al umbral (o reinicia el cooldown si ya estaba abierto);
    'up' cierra (resetea); 'neutral' no toca. Puro (recibe `now`)."""
    for h in hosts:
        rec = targets_state.setdefault(h, {"fails": 0, "opened_at": None})
        if verdict == "fail":
            rec["fails"] = int(rec.get("fails", 0)) + 1
            if rec["fails"] >= threshold:
                rec["opened_at"] = now  # abre, o reinicia el cooldown si un sondeo medio-abierto volvió a fallar
        elif verdict == "up":
            rec["fails"] = 0
            rec["opened_at"] = None
    return targets_state


def _split_response(event):
    """Devuelve (stderr_text, full_text) de la salida del comando (PostToolUse). Aísla STDERR para que
    los fallos de CONEXIÓN se busquen SOLO ahí (curl/ssh los emiten por stderr) y el BODY de la
    respuesta (stdout, controlado por el target) no pueda disparar el breaker. Si la forma no permite
    aislar stderr (tool_response es un string plano), stderr='' → CONSERVADOR: no se cuentan fallos de
    conexión sobre el body; solo señales de host-vivo y frases tool-self (nmap/ping)."""
    tr = event.get("tool_response")
    if isinstance(tr, dict):
        stderr = str(tr.get("stderr") or "")
        stdout = str(tr.get("stdout") or "")
        return stderr, (stdout + "\n" + stderr).strip()
    if isinstance(tr, str):
        return "", tr
    return "", ("" if tr is None else str(tr))


def _scoped_domains():
    try:
        with open(SCOPE, encoding="utf-8") as f:
            s = json.load(f)
        return (s.get("in_scope", {}).get("domains", []) or []) + \
               (s.get("out_of_scope", {}).get("domains", []) or [])
    except Exception:
        return []


def _targets(command):
    """Extrae hosts/IPs del comando reutilizando scope_guard (no divergir en la extracción)."""
    try:
        sys.path.insert(0, HOOKS_DIR)
        import scope_guard
        return scope_guard.extract_targets(command, _scoped_domains())
    except Exception:
        return set()


def _deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    sys.exit(0)


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if event.get("tool_name") != "Bash":
        sys.exit(0)
    command = (event.get("tool_input") or {}).get("command", "") or ""
    if not command:
        sys.exit(0)

    hosts = _targets(command)
    if not hosts:
        sys.exit(0)  # comando sin target de red: no nos incumbe

    key = _engagement_key()
    threshold, cooldown = _config()
    state = load_state(key)
    now = int(time.time())

    is_post = event.get("hook_event_name") == "PostToolUse" or "tool_response" in event

    if is_post:
        stderr_text, full_text = _split_response(event)
        verdict = classify(stderr_text, full_text, command)
        if verdict != "neutral":
            record_outcome(state, hosts, verdict, now, threshold)
            save_state(key, state)
        sys.exit(0)

    # PreToolUse: bloquea si algún target tiene el breaker abierto (cooldown sin cumplir).
    h, rec = open_breaker_target(state, hosts, now, cooldown)
    if h:
        remaining = cooldown - (now - rec["opened_at"])
        _deny(
            f"circuit_breaker (C22): el target «{h}» parece CAÍDO/inalcanzable — {rec.get('fails')} "
            f"fallos de conexión consecutivos (rechazo/timeout/DNS/host-down). Deja de machacarlo: "
            f"verifica la reachability (¿pivot 'down'? ¿fuera de la ventana de pruebas? ¿IP baneada = "
            f"'burned' → pasa a OSINT pasivo, §9?). Reintenta tras el cooldown (~{max(remaining,0)}s) o "
            f"borra contracts/.circuit_state para resetear. NO es el cierre: el host sale de la frontera "
            f"activa hasta que responda; pivota a otro vector/host.")
    sys.exit(0)


if __name__ == "__main__":
    main()
