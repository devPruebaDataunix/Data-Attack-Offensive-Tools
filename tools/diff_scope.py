#!/usr/bin/env python3
"""
diff_scope.py — DIFF-SCOPE PR-aware para la revisión white-box (mejora v2.60; idea de strix, Apache-2.0
→ reimplementación limpia, solo stdlib). Cuando el engagement revisa un PR / una rama (no todo el repo),
`code-recon` debe centrarse en la SUPERFICIE CAMBIADA, no releer el árbol entero. Esta herramienta calcula
los ficheros modificados entre un `diff_base` (rama/commit de referencia) y HEAD del checkout LOCAL del
repo y los deja como PISTA priorizada para que `code-recon` (que no tiene Bash) lea y ATAQUE primero lo
que el PR toca.

`code-recon` NO tiene Bash (el código es inerte): esta herramienta la corre el ORQUESTADOR como paso de
recon-prep (o el operador) DENTRO del anillo efímero (mejora C), y escribe el resultado en
`engagements/<id>/recon/diff-<repo_id>.json`. `code-recon` lo lee con Read.

Seguridad (paridad con fs_guard / el confinamiento de code-recon):
- **Checkout confinado.** El `local_path` DEBE vivir bajo `engagements/<id>/recon/src/` del repo
  (realpath; rechaza traversal/symlink) — el código es dato de cliente (E3) y ahí es donde lo deposita el
  operador. No se corre `git` sobre un path arbitrario del sistema.
- **Sin inyección de opciones.** El `diff_base` se valida (ref plausible; nunca empieza por `-`) y se pasa
  como argumento posicional tras `--` a un `git` invocado por LISTA (sin shell) — no puede colar una
  opción (`--upload-pack=…`) ni un comando.
- **Solo lectura + sin red.** `git diff --name-only` no muta el repo ni sale a la red; no clona (el
  checkout ya lo provee el operador). Al blackboard/artefacto solo van RUTAS relativas, nunca código.

Uso:
    python tools/diff_scope.py --repo app-backend                 # lee local_path+diff_base de scope.json
    python tools/diff_scope.py --repo app-backend --base main --out engagements/<id>/recon/diff-app-backend.json
    python tools/diff_scope.py --path engagements/<id>/recon/src/app-backend --base v1.2.0
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_MARKER = os.path.join("recon", "src")
# Ref de git plausible: alfanumérico + los separadores válidos de una revisión. NUNCA empieza por '-'
# (evita que un `diff_base` hostil se interprete como opción de git).
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./@^~{}-]*$")

sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
try:
    from scope_guard import load_scope
except Exception:  # noqa: BLE001
    load_scope = None


def _err(msg):
    print(f"diff_scope: {msg}", file=sys.stderr)


def valid_ref(base):
    """¿Es `base` una referencia de git plausible y NO una opción/inyección?"""
    return isinstance(base, str) and bool(_REF_RE.match(base)) and ".." not in base


def confined_checkout(local_path):
    """Resuelve `local_path` confinado bajo engagements/<id>/recon/src/ del repo (realpath; rechaza
    traversal/symlink). Devuelve la ruta real o lanza ValueError."""
    eng_base = os.path.realpath(os.path.join(ROOT, "engagements"))
    real = os.path.realpath(local_path if os.path.isabs(local_path) else os.path.join(ROOT, local_path))
    if real != eng_base and not real.startswith(eng_base + os.sep):
        raise ValueError(f"el checkout debe estar bajo engagements/ del repo (no '{local_path}')")
    # Debe estar dentro de un .../recon/src/... (donde el operador deposita el código de cliente).
    if (os.sep + SRC_MARKER + os.sep) not in real + os.sep:
        raise ValueError(f"el checkout debe vivir bajo <id>/recon/src/ (no '{local_path}')")
    if not os.path.isdir(real):
        raise ValueError(f"el checkout no existe o no es un directorio: '{local_path}'")
    return real


def _repo_conf(repo_id):
    """Saca (local_path, diff_base) de scope.json → source_repos[repo_id]. None si no está."""
    if load_scope is None:
        return None
    scope = load_scope()
    for r in ((scope or {}).get("source_repos") or []):
        if isinstance(r, dict) and r.get("repo_id") == repo_id:
            return r.get("local_path"), r.get("diff_base")
    return None


def changed_files(checkout, base):
    """Ficheros cambiados entre `base` y HEAD del checkout (git diff --name-only base...HEAD). Lista
    ordenada de rutas relativas al repo. Lanza RuntimeError si git falla / no es un repo."""
    if not valid_ref(base):
        raise ValueError(f"diff_base no es una referencia de git válida: '{base}'")
    # `base...HEAD` (tres puntos) = cambios en HEAD desde el ancestro común con base (semántica de PR).
    # El checkout es CÓDIGO DE CLIENTE = contenido HOSTIL: neutralizamos vectores de config del repo
    # (`core.fsmonitor`/hooks lanzan comandos) y la config de sistema — defensa en profundidad sobre el
    # anillo efímero. `-c` va ANTES del subcomando; el subcomando `diff` no dispara hooks, esto es cinturón.
    cmd = ["git", "-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null",
           "-C", checkout, "diff", "--name-only", f"{base}...HEAD", "--"]
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    except FileNotFoundError:
        raise RuntimeError("git no está instalado en este entorno (córrelo en el anillo efímero).")
    except subprocess.TimeoutExpired:
        raise RuntimeError("git diff excedió el tiempo límite.")
    if p.returncode != 0:
        raise RuntimeError(f"git diff falló (¿'{base}' existe? ¿es un repo?): {p.stderr.strip()}")
    files = sorted({ln.strip() for ln in p.stdout.splitlines() if ln.strip()})
    return files


def build(repo_id, checkout, base):
    return {"repo_id": repo_id or os.path.basename(checkout.rstrip(os.sep)), "diff_base": base,
            "changed_files": changed_files(checkout, base), }


def _confined_out(path):
    """--out confinado bajo engagements/ del repo (igual criterio que el checkout)."""
    base = os.path.realpath(os.path.join(ROOT, "engagements"))
    real = os.path.realpath(path if os.path.isabs(path) else os.path.join(ROOT, path))
    parent = os.path.realpath(os.path.dirname(real))
    if parent != base and not parent.startswith(base + os.sep):
        raise ValueError(f"--out debe estar bajo engagements/ del repo (no '{path}')")
    return real


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diff-scope PR-aware para code-recon (ficheros cambiados).",
                                 allow_abbrev=False)
    ap.add_argument("--repo", default=None, help="repo_id de scope.json → source_repos[] (saca local_path+diff_base).")
    ap.add_argument("--path", default=None, help="checkout local (alternativa a --repo); bajo <id>/recon/src/.")
    ap.add_argument("--base", default=None, help="diff_base (rama/commit de referencia; def.: el de scope.json).")
    ap.add_argument("--out", default=None, help="fichero de salida bajo engagements/ (def.: stdout).")
    args = ap.parse_args(argv)

    local_path, base = args.path, args.base
    if args.repo:
        conf = _repo_conf(args.repo)
        if conf is None:
            _err(f"repo_id '{args.repo}' no está en scope.json → source_repos[]"); return 2
        local_path = local_path or conf[0]
        base = base or conf[1]
    if not local_path:
        _err("hace falta --repo (con local_path en scope.json) o --path"); return 2
    if not base:
        _err("hace falta --base (o un diff_base en scope.json → source_repos[])"); return 2

    try:
        checkout = confined_checkout(local_path)
        data = build(args.repo, checkout, base)
    except ValueError as e:
        _err(str(e)); return 3
    except RuntimeError as e:
        _err(str(e)); return 4

    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        try:
            dst = _confined_out(args.out)
        except ValueError as e:
            _err(str(e)); return 3
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as e:
            _err(f"no se pudo escribir '{args.out}': {e}"); return 3
        print(os.path.relpath(dst, ROOT).replace("\\", "/"))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
