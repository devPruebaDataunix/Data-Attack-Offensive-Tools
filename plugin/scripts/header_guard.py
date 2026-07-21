#!/usr/bin/env python3
"""
header_guard.py — Hook PreToolUse (Claude Code) que impone la cabecera HTTP obligatoria del programa.

Barrera DETERMINISTA para engagements (típicamente bug bounty) que EXIGEN identificar tu tráfico
con una cabecera fija — p.ej. Bugcrowd: "add BUGCROWD and your handle to your traffic headers",
`BUGCROWD: <handle>`. Si `contracts/scope.json` declara `constraints.required_http_header`, este hook
inspecciona cada comando Bash y BLOQUEA (fail-closed) cualquier invocación de una herramienta HTTP
conocida contra un target cuando la cabecera NO va en un flag de cabecera real (‑H/‑‑header/…). No
depende de ningún LLM. Cuando el scope NO declara `required_http_header`, el hook es no-op.

ALCANCE HONESTO (léelo — es una red de seguridad de MEJOR ESFUERZO, no una garantía total):
- Verifica que la cabecera va en un **flag de cabecera** (‑H, ‑‑header, ‑‑headers, ‑header) del comando,
  no en cualquier parte de la línea (así no cuela por la URL, el body ‑d, el user-agent ‑A, un comentario
  o un nombre de fichero).
- Cubre las herramientas HTTP de CLI más comunes (curl/wget/httpx/ffuf/feroxbuster/gobuster/dirsearch/
  nuclei/sqlmap/katana/wpscan/dalfox/wfuzz/gospider/xh/hurl…), incluidas ejecutadas como script
  (`python3 sqlmap.py`). Herramientas que NO saben poner una cabecera arbitraria por CLI (nikto, whatweb,
  wafw00f, testssl.sh) quedan como **solo-proxy**: pásalas por un proxy que inyecte la cabecera.
- Un comando con **proxy explícito** (‑x/‑‑proxy o envuelto en proxychains) se EXIME: se asume que el
  operador configuró el proxy para inyectar la cabecera (responsabilidad del operador, documentada).
- El CUERPO de un here-document (`cat > f <<EOF … EOF`) se trata como DATO, no como comando: escribir un
  script o un resumen que *menciona* una herramienta HTTP no es lanzarla. El caso exótico de ejecutar un
  heredoc (`bash <<EOF … EOF`) queda, por tanto, fuera de cobertura (igual que `bash script.sh`).
- Lo que el gate NO puede ver y sigue siendo responsabilidad del operador: binarios compilados propios,
  intérpretes crudos (`python -c "import requests…"`), httpie (`http`) y clientes con sintaxis de cabecera
  no estándar, navegadores headless, tráfico por `WebFetch`/MCP (este hook solo mira `Bash`), y proxies que
  no inyecten de verdad. NO asumas cobertura total; es una red de seguridad, no una garantía.

Protocolo Claude Code (idéntico a scope_guard.py): recibe JSON por stdin; para BLOQUEAR imprime la
decisión deny y sale 0. Solo stdlib.
"""
import json
import os
import re
import shlex
import sys

SCOPE_CANDIDATES = [
    os.path.join("contracts", "scope.json"),
    os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "scope.json"),
]

# Herramientas que EMITEN peticiones HTTP contra el target. El gate exige que lleven la cabecera en un
# flag de cabecera real (o que vayan por proxy). Las que no saben poner cabecera por CLI (nikto, whatweb,
# wafw00f, testssl.sh, httpie/http) quedan como solo-proxy. Se excluyen a propósito las PASIVAS (subfinder/
# amass/gau/waybackurls: no tocan el target) y el escaneo de puertos (nmap: TCP, sin cabecera HTTP — salvo
# NSE http-*, que el operador debe proxyficar; ver docstring). Ampliable con constraints.http_tools_extra.
HTTP_TOOLS = {
    "curl", "wget", "httpx", "httprobe", "ffuf", "feroxbuster", "gobuster", "dirsearch",
    "dirb", "nuclei", "sqlmap", "katana", "hakrawler", "wfuzz", "wpscan", "dalfox", "arjun",
    "kiterunner", "kr", "meg", "x8", "gospider", "xh", "hurl",
    "nikto", "whatweb", "wafw00f", "testssl.sh", "testssl",  # solo-proxy (sin -H arbitrario por CLI)
}
# Sufijos de script que se strippean para reconocer la herramienta ejecutada por intérprete
# (`python3 sqlmap.py`, `./dirsearch.py`, `ruby wpscan.rb`).
SCRIPT_SUFFIXES = (".py", ".rb", ".pl", ".sh")

# Flags que llevan una cabecera HTTP arbitraria (curl/httpx/ffuf/nuclei/sqlmap/wget/wpscan…).
HEADER_FLAGS = {"-H", "--header", "--headers", "-header", "-headers"}

# Prefijos que envuelven al binario real (se saltan para detectar la herramienta y el proxy).
WRAPPERS = {"sudo", "time", "nice", "stdbuf", "timeout", "nohup", "setsid", "env", "doas"}
PROXY_WRAPPERS = {"proxychains", "proxychains4"}
# Flags que indican que el tráfico va por un proxy gestionado por el operador (inyecta la cabecera).
PROXY_FLAGS = {"-x", "--proxy", "--preproxy", "--proxy-ntlm", "--proxychains"}

# Sub-comandos de mantenimiento (no lanzan tráfico al target). Se evitan flags cortos ambiguos
# (‑h/‑V/‑tl…) que colisionan con flags de scan reales; solo formas inequívocas.
EXEMPT_FLAGS = {"--version", "-version", "--help", "-help", "-update", "-up", "-update-templates",
                "-duc", "-disable-update-check", "-update-template-dir"}


def deny(reason: str):
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
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
    return None


# `(?<!<)<<(?!<)` casa el operador heredoc `<<` pero NO el here-string `<<<` (que es de una sola
# línea y NO abre cuerpo). El delimitador es una palabra, opcionalmente citada (`<<'EOF'`).
HEREDOC_OPEN_RE = re.compile(r"(?<!<)<<(?!<)[-~]?\s*(['\"]?)([A-Za-z_]\w*)\1")


def _in_quote_or_comment(prefix: str) -> bool:
    """True si el final de `prefix` cae dentro de una comilla o de un comentario `#`. Se usa para
    descartar un `<<` que aparece dentro de un string/comentario (`echo "a << b"`, `# ver <<x`): ahí
    NO es un operador de redirección, así que no debe abrir modo 'saltar cuerpo'."""
    sq = dq = False
    i = 0
    while i < len(prefix):
        c = prefix[i]
        if c == "\\" and dq:
            i += 2
            continue
        if c == "'" and not dq:
            sq = not sq
        elif c == '"' and not sq:
            dq = not dq
        elif c == "#" and not sq and not dq:
            return True  # comentario hasta fin de línea
        i += 1
    return sq or dq


def _line_openers(line: str):
    """Aperturas de heredoc REALES en `line`: excluye `<<<` (ancla) y los `<<` dentro de comillas o
    comentario. Devuelve [(delimitador, admite_indentado)]."""
    res = []
    for m in HEREDOC_OPEN_RE.finditer(line):
        if _in_quote_or_comment(line[: m.start()]):
            continue
        dashed = m.group(0)[2:3] in ("-", "~")
        res.append((m.group(2), dashed))
    return res


def strip_heredocs(command: str) -> str:
    """Elimina el CUERPO de los here-documents (`cmd <<EOF … EOF`, `cat > f <<'EOF' … EOF`).

    El cuerpo de un heredoc es DATO que se escribe a un fichero/variable/`cat`, no una invocación:
    un script o un resumen que *menciona* `nuclei -u https://… -tags …` no está lanzando nuclei. Sin
    esto, `split_subcommands` troceaba por saltos de línea y leía esa línea del cuerpo como si fuera
    una invocación HTTP sin cabecera => falso positivo al escribir ficheros.

    FAIL-CLOSED por diseño: solo se entra en modo 'saltar cuerpo' si (a) el `<<` es un operador real
    (no `<<<`, ni dentro de comillas/comentario) y (b) EXISTE más adelante la línea terminadora con el
    delimitador. Un `<<palabra` espurio (here-string, string, comentario, left-shift `$((1<<n))`) casi
    nunca tiene esa terminadora, así que NO se salta nada y esas líneas se ESCANEAN (fail-closed) — se
    cierra el bypass que abriría un `curl` sin cabecera tras un `<<` falso. Se conserva SIEMPRE la línea
    de apertura (lleva el comando real, p.ej. `cat > f`). Residual honesto: ejecutar un heredoc real
    (`bash <<EOF … curl … EOF`) queda fuera de cobertura, igual que `bash script.sh`."""
    lines = command.split("\n")
    n = len(lines)
    keep = [True] * n
    i = 0
    while i < n:
        openers = _line_openers(lines[i])
        if not openers:
            i += 1
            continue
        j = i + 1
        for delim, dashed in openers:  # FIFO, como bash con varios heredocs en una línea
            term_idx = None
            for k in range(j, n):
                t = lines[k].strip() if dashed else lines[k].rstrip()
                if t == delim:
                    term_idx = k
                    break
            if term_idx is None:
                break  # sin terminadora: NO es cuerpo de heredoc -> no se salta (fail-closed)
            for x in range(j, term_idx + 1):
                keep[x] = False   # cuerpo + terminadora: dato, no se escanea
            j = term_idx + 1
        i = max(j, i + 1)
    return "\n".join(l for l, k in zip(lines, keep) if k)


def join_continuations(command: str) -> str:
    """Une las continuaciones de línea de shell (`\\` + salto) para no trocear un comando que el
    shell trataría como una sola línea (evita falsos positivos con comandos multilínea)."""
    return re.sub(r"\\\r?\n", " ", command)


def split_subcommands(command: str):
    """Trocea por separadores de shell (| || && ; & y saltos). No es un parser de shell completo;
    suficiente para aislar cada invocación de herramienta."""
    return [p for p in re.split(r"\|\||&&|[|;\n&]", command) if p.strip()]


def tokenize(subcmd: str):
    """shlex respeta comillas (mantiene `-H "X: Y"` como un token). Fallback a split() si el trozo
    tiene comillas/escapes desbalanceados."""
    try:
        return shlex.split(subcmd)
    except Exception:
        return [t.strip("'\"") for t in subcmd.split()]


def _base(tok: str) -> str:
    b = tok.rsplit("/", 1)[-1]
    for suf in SCRIPT_SUFFIXES:
        if b.endswith(suf):
            return b[: -len(suf)]
    return b


def http_tool_in(tokens, tools) -> bool:
    for t in tokens:
        if not t or t.startswith("-"):
            continue
        if "=" in t and not t.startswith("/") and "/" not in t:  # asignación VAR=val
            continue
        if _base(t) in tools:
            return True
    return False


def uses_proxy(tokens) -> bool:
    if any(_base(t) in PROXY_WRAPPERS for t in tokens):
        return True
    for t in tokens:
        if t in PROXY_FLAGS or any(t.startswith(f + "=") for f in PROXY_FLAGS):
            return True
    return False


def is_exempt(tokens) -> bool:
    return bool(set(tokens) & EXEMPT_FLAGS)


def _norm(s: str) -> str:
    # colapsa espacios alrededor de ':' y baja a minúsculas para tolerar `X: Y` / `X:Y` y case.
    return re.sub(r"\s*:\s*", ":", s).lower()


def header_values(tokens):
    """Devuelve los valores pasados en flags de cabecera reales (‑H "X: Y", ‑‑header=X: Y)."""
    vals = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in HEADER_FLAGS:
            if i + 1 < len(tokens):
                vals.append(tokens[i + 1])
            i += 2
            continue
        for f in HEADER_FLAGS:
            if t.startswith(f + "="):
                vals.append(t[len(f) + 1:])
                break
        i += 1
    return vals


def header_present(tokens, name: str, value: str) -> bool:
    need = f"{name.strip().lower()}:{value.strip().lower()}"
    return any(need in _norm(v) for v in header_values(tokens))


def header_gate(command: str, required_header: str, extra_tools=None):
    """Devuelve un motivo de bloqueo (str) si algún sub-comando invoca una herramienta HTTP conocida
    contra un target sin la cabecera requerida en un flag de cabecera (y sin proxy); None si conforme.
    Función PURA (testeable sin stdin/red). El motivo NO ecoa el comando (evita filtrar secretos)."""
    if not required_header or ":" not in required_header:
        return None
    name, value = required_header.split(":", 1)
    name, value = name.strip(), value.strip()
    if not name or not value:
        return None
    tools = set(HTTP_TOOLS)
    if extra_tools:
        tools |= {str(t) for t in extra_tools}

    for sub in split_subcommands(join_continuations(strip_heredocs(command))):
        toks = tokenize(sub)
        if not http_tool_in(toks, tools):
            continue
        if is_exempt(toks) or uses_proxy(toks):
            continue
        if not header_present(toks, name, value):
            tool = next((_base(t) for t in toks
                         if t and not t.startswith("-") and _base(t) in tools), "una herramienta HTTP")
            return (f"Falta la cabecera obligatoria del programa «{name}: {value}» en un comando que "
                    f"invoca «{tool}». El programa EXIGE identificar TODO el tráfico con esa cabecera. "
                    f"Añádela en un flag de cabecera (p.ej. -H \"{name}: {value}\", o sqlmap "
                    f"--header=\"{name}: {value}\"), o enruta el comando por un proxy que la inyecte "
                    f"(-x / proxychains). Bloqueado por header_guard (fail-closed).")
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if event.get("tool_name") != "Bash":
        sys.exit(0)

    command = (event.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    scope = load_scope()
    if not scope:
        sys.exit(0)
    constraints = scope.get("constraints", {}) or {}
    required = constraints.get("required_http_header", "")
    extra = constraints.get("http_tools_extra", [])

    reason = header_gate(command, required, extra)
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
