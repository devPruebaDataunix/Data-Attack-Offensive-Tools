#!/usr/bin/env python3
"""
fs_guard.py — Hook PreToolUse que CONFINA las lecturas de fichero (Read/Grep/Glob) para que el
código de cliente (zona E3) no pueda pivotar la lectura hacia fuera de su sitio. Es la barrera
EN-PROCESO que cierra el hueco que la mejora "A" (code-recon, white-box) dejó diferido: `code-recon`
lee un repositorio de cliente que es contenido POTENCIALMENTE HOSTIL (E3) y un repo envenenado
podría plantar un symlink `recon/src/leak -> /root/.claude/...` (exfiltrar credenciales del operador)
o `-> ../../<otro-id>/loot/` (contaminar otro engagement), tener el propio ancla `recon/src`
symlinkeada, o pasar una ruta con `../../../etc/passwd`.

Es COMPLEMENTARIA al contenedor efímero por-engagement (mejora C, el anillo de namespace de montaje):
el contenedor da el confinamiento DURO (el proceso solo ve `engagements/<id>/`); este guard da la
barrera determinista que funciona AUNQUE se corra directo sobre el host (Kali) sin contenedor.

Modelo de amenaza (lo que SÍ bloquea, fail-closed ante violación CLARA):
- (crown jewel) Cualquier lectura cuyo destino real caiga bajo `~/.claude` (credenciales del operador),
  sea por symlink o por ruta absoluta directa. La tool `Read` no tiene por qué tocar ese árbol.
- (ancla) Cualquier ruta bajo `engagements/<id>/recon/src/` cuyo **ancla misma** (`recon/src` o un
  padre) sea un symlink que resuelva FUERA del repo — el vector de un checkout de cliente entregado
  con `recon/src` ya symlinkeado a `~/.claude`.
- (C) Cualquier ruta bajo `recon/src/` cuyo destino REAL (symlinks) o su normalización léxica (`..`)
  escape de ESE árbol `src/`. El código es inerte: una pista solo referencia ficheros DENTRO del
  checkout; salirse (a otro engagement, al repo, al sistema) es un ataque.
- (B) Symlink INTERNO del repo (fuera de src/) que resuelve FUERA del repo.

Cobertura por herramienta (SIN sobre-promesa): para `Read` se verifica el `file_path` exacto. Para
`Grep`/`Glob` se verifica el `path` de la CONSULTA (su raíz), no cada fichero que la herramienta
recorre por dentro — ripgrep/Glob no siguen symlinks por defecto, y el confinamiento DURO del recorrido
profundo de Grep/Glob lo aporta el CONTENEDOR efímero (montaje mínimo), no este guard.

Lo que deliberadamente NO hace: confinar TODA lectura absoluta al repo. Una lectura absoluta a un
fichero del propio host del operador que NO sea `~/.claude` (p.ej. el scratchpad, un wordlist) no es
una fuga de datos de CLIENTE; el confinamiento de todo el FS del host es trabajo del contenedor.

Protocolo Claude Code (igual que memory_guard.py / scope_guard.py):
- Recibe JSON por stdin: {"tool_name","tool_input":{...}}.
- Para BLOQUEAR: imprime la decisión PreToolUse (permissionDecision=deny) y sale 0.
- Cualquier ambigüedad (no es Read/Grep/Glob, sin ruta, error) => sale 0 (fail-open: un guard nunca
  rompe el flujo; el bloqueo es solo ante violación clara).

Solo stdlib. Sin dependencias.
"""
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))

# Credenciales del operador: `~/.claude` (donde vive .credentials.json / el token OAuth). Nunca es
# un destino legítimo de la tool Read en un engagement. Se resuelve una vez al cargar.
try:
    HOME_CLAUDE = os.path.normcase(os.path.realpath(os.path.join(os.path.expanduser("~"), ".claude"))).replace("\\", "/")
except Exception:  # noqa: BLE001
    HOME_CLAUDE = None

# Ancla del código de cliente: `.../engagements/<id>/recon/src`. Se detecta sobre la ruta CRUDA con
# separadores colapsados (pre-normalización de `..`): un traversal (`recon/src/../../etc`) deja el
# prefijo `recon/src` literal ANTES de los `..`. `re.I` + normcase para casar en Windows y POSIX.
SRC_ANCHOR_RE = re.compile(r"^(.*?/engagements/[^/]+/recon/src)(?:/|$)", re.I)


def _norm(p):
    """Ruta absoluta normalizada léxica (colapsa `..`), normcase, con `/`. NO resuelve symlinks."""
    return os.path.normcase(os.path.normpath(p)).replace("\\", "/")


def _real(p):
    """Ruta absoluta con symlinks RESUELTOS, normcase, con `/`."""
    return os.path.normcase(os.path.realpath(p)).replace("\\", "/")


def _collapse(fs):
    """Colapsa `//` y `/./` preservando `..` — para que el ancla `recon/src` no se evada con
    `recon//src` o `recon/./src` cayendo al caso (B), más laxo."""
    fs = re.sub(r"/+", "/", fs)
    prev = None
    while prev != fs:
        prev = fs
        fs = re.sub(r"/\./", "/", fs)
    return re.sub(r"/\.$", "", fs)


def under(child, parent):
    """True si `child` es `parent` o cuelga de él (sin el bug de prefijo `/a/b` vs `/a/bc`)."""
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def candidate_paths(tool_name, tool_input):
    """Rutas de fichero que la herramienta va a TOCAR (las que hay que verificar)."""
    ti = tool_input or {}
    out = []
    if tool_name == "Read":
        fp = ti.get("file_path")
        if fp:
            out.append(fp)
    elif tool_name in ("Grep", "Glob"):
        p = ti.get("path")  # opcional; si falta, es el cwd (dentro del repo) => nada que verificar
        if p:
            out.append(p)
    return [p for p in out if isinstance(p, str) and p]


def violation(raw_path):
    """Devuelve un motivo (str) si `raw_path` viola el confinamiento, o None si es admisible.

    Determinista y puro (testeable). `raw_path` es la ruta tal cual la pide la herramienta
    (absoluta o relativa al repo)."""
    if not raw_path:
        return None
    joined = raw_path if os.path.isabs(raw_path) else os.path.join(ROOT, raw_path)
    # normcase ANTES de forzar `/` (en Windows normcase convierte `/`->`\`; si se hiciera después
    # rompería el regex del ancla, que casa sobre `/`). Conserva `..` (no normaliza la ruta).
    probe = _collapse(os.path.normcase(joined).replace("\\", "/"))  # crudo colapsado (detecta el ancla)
    lex = _norm(joined)                              # normalizado léxico (colapsa `..`), sin symlinks
    try:
        real = _real(joined)                         # symlinks resueltos
    except Exception:  # noqa: BLE001 — sin poder resolver, no interferimos
        return None
    root_lex = _norm(ROOT)
    root_real = _real(ROOT)

    # (crown jewel) el destino real NUNCA puede caer bajo ~/.claude (credenciales del operador),
    # sea por symlink o por ruta absoluta directa. Backstop del modo host (sin contenedor).
    if HOME_CLAUDE and under(real, HOME_CLAUDE):
        return (f"la ruta resuelve dentro de ~/.claude (credenciales del operador) — {real}")

    # (C) La ruta ENTRA en código de cliente (`recon/src`): su ancla, su destino real y su
    # normalización léxica deben quedar DENTRO de ese mismo árbol `src/` (y del repo).
    m = SRC_ANCHOR_RE.match(probe)
    if m:
        src_root = m.group(1)                        # ya colapsado + normcase, con `/`
        src_real = _real(src_root)
        # El ancla misma no puede resolver FUERA del repo (symlink en recon/src o un padre).
        if not under(src_real, root_real):
            return (f"el árbol de código de cliente resuelve FUERA del repo "
                    f"(recon/src -> {src_real}); ancla comprometida (symlink en recon/src o un padre)")
        if not under(lex, src_root):
            return (f"la ruta se sale del código de cliente por traversal `..` "
                    f"(pedida bajo {src_root}, resuelve a {lex})")
        if not under(real, src_real):
            return (f"un symlink dentro del código de cliente apunta FUERA de su árbol "
                    f"(recon/src -> {real}); el código es E3 y debe ser inerte")
        # Defensa en profundidad: nada en (C) puede salir del repo por ninguna vía.
        if not under(real, root_real):
            return (f"la ruta bajo código de cliente resuelve FUERA del repo ({real})")
        return None

    # (B) Symlink INTERNO del repo que escapa del repo: la ruta léxica está dentro del repo pero su
    # destino real sale. Se compara lex-vs-lex y real-vs-real (consistente en casing y symlinks del
    # propio ROOT). Una ruta absoluta fuera del repo SIN symlink no se gatea aquí (no es dato de
    # cliente y su confinamiento es del contenedor; salvo ~/.claude, ya cubierto arriba).
    if under(lex, root_lex) and not under(real, root_real):
        return (f"un symlink dentro del repo apunta FUERA del árbol del proyecto "
                f"({lex} -> {real})")

    return None


def deny(raw_path, reason):
    msg = (
        "fs_guard: lectura BLOQUEADA por confinamiento del código de cliente (CONSTITUTION §1/§6, "
        f"aislamiento E3): {reason}. Ruta: {raw_path}. El código de cliente vive y se lee SOLO dentro "
        "de `engagements/<id>/recon/src/`; no sigas symlinks que salgan de ahí ni uses `..` para "
        "escapar, y nunca leas `~/.claude`. Si necesitas un fichero legítimo, refiérelo por su ruta "
        "real dentro del árbol."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": msg,
        }
    }))
    sys.exit(0)


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    tool_name = event.get("tool_name")
    if tool_name not in ("Read", "Grep", "Glob"):
        sys.exit(0)

    for raw in candidate_paths(tool_name, event.get("tool_input") or {}):
        reason = violation(raw)
        if reason:
            deny(raw, reason)
    sys.exit(0)  # todas las rutas admisibles => permitir


if __name__ == "__main__":
    main()
