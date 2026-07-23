#!/usr/bin/env python3
"""Tests del DIFF-SCOPE PR-aware (mejora v2.60 — idea de strix).

Cubre `tools/diff_scope.py`: validación de la ref (anti-inyección de opciones), confinamiento del checkout
a engagements/<id>/recon/src/, y (si hay git) el cálculo real de ficheros cambiados.

    python tests/test_diff_scope.py    (sale 1 si algo falla).
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


import diff_scope as ds  # noqa: E402

# ── valid_ref: anti-inyección de opciones ───────────────────────────────────────────
check("valid_ref acepta ramas/commits normales",
      ds.valid_ref("main") and ds.valid_ref("v1.2.0") and ds.valid_ref("a1b2c3d") and ds.valid_ref("release/x"))
check("valid_ref rechaza opción de git (empieza por '-')", not ds.valid_ref("--upload-pack=x") and not ds.valid_ref("-x"))
check("valid_ref rechaza '..' (rango) y vacío", not ds.valid_ref("a..b") and not ds.valid_ref(""))
check("valid_ref rechaza metacaracteres", not ds.valid_ref("a;rm -rf") and not ds.valid_ref("a b"))

# ── confinamiento del checkout ───────────────────────────────────────────────────────
SRC = os.path.join(ROOT, "engagements", "_ds_test", "recon", "src", "repo")
os.makedirs(SRC, exist_ok=True)
try:
    check("confined_checkout acepta un dir bajo <id>/recon/src/", ds.confined_checkout(SRC) == os.path.realpath(SRC))
except Exception as e:  # noqa: BLE001
    check("confined_checkout acepta un dir bajo <id>/recon/src/", False)

def _rejects(p):
    try:
        ds.confined_checkout(p)
        return False
    except ValueError:
        return True

check("rechaza checkout fuera de engagements/", _rejects(os.path.join(ROOT, "tools")))
check("rechaza checkout bajo engagements/ pero sin recon/src/",
      _rejects(os.path.join(ROOT, "engagements", "_ds_test")))
check("rechaza traversal", _rejects(os.path.join(ROOT, "engagements", "_ds_test", "recon", "src", "..", "..", "..", "..", "tools")))

# ── changed_files: git real (skip si no hay git) ─────────────────────────────────────
have_git = shutil.which("git") is not None
if have_git:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    def g(*args):
        return subprocess.run(["git", "-C", SRC, *args], capture_output=True, text=True, env=env)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t.local"); g("config", "user.name", "t"); g("config", "commit.gpgsign", "false")
    with open(os.path.join(SRC, "base.txt"), "w") as f:
        f.write("base\n")
    g("add", "-A"); g("commit", "-q", "-m", "base")
    g("checkout", "-q", "-b", "feature")
    with open(os.path.join(SRC, "new.py"), "w") as f:
        f.write("print(1)\n")
    g("add", "-A"); g("commit", "-q", "-m", "feature adds new.py")
    files = ds.changed_files(SRC, "main")
    check("changed_files(main) detecta el fichero del PR", "new.py" in files and "base.txt" not in files)
    # ref inexistente -> RuntimeError
    try:
        ds.changed_files(SRC, "no-such-ref")
        check("ref inexistente -> RuntimeError", False)
    except RuntimeError:
        check("ref inexistente -> RuntimeError", True)
    # ref inválida -> ValueError (no llega a git)
    try:
        ds.changed_files(SRC, "--upload-pack=x")
        check("ref inválida -> ValueError (anti-inyección)", False)
    except ValueError:
        check("ref inválida -> ValueError (anti-inyección)", True)
    # build() estructura
    b = ds.build("repo", SRC, "main")
    check("build() devuelve repo_id/diff_base/changed_files",
          b["repo_id"] == "repo" and b["diff_base"] == "main" and "new.py" in b["changed_files"])
    # base == HEAD -> sin cambios (lista vacía)
    check("changed_files(HEAD) sin cambios -> []", ds.changed_files(SRC, "HEAD") == [])
    # CLI --out: escribe bajo engagements/ y rechaza fuera
    rel = os.path.join("engagements", "_ds_test", "recon", "diff-repo.json")
    r_ok = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "diff_scope.py"),
                           "--path", SRC, "--base", "main", "--out", rel],
                          capture_output=True, text=True)
    check("CLI --out bajo engagements/ -> exit 0 + fichero",
          r_ok.returncode == 0 and os.path.isfile(os.path.join(ROOT, rel)))
    r_bad = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "diff_scope.py"),
                            "--path", SRC, "--base", "main", "--out", "tools/evil.json"],
                           capture_output=True, text=True)
    check("CLI --out fuera de engagements/ -> exit 3, sin escribir",
          r_bad.returncode == 3 and not os.path.exists(os.path.join(ROOT, "tools", "evil.json")))
else:
    print("  (git no disponible: se omiten los tests de changed_files)")

# limpieza
shutil.rmtree(os.path.join(ROOT, "engagements", "_ds_test"), ignore_errors=True)

print()
if _fail:
    print(f"FALLOS: {len(_fail)} -> {_fail}")
    sys.exit(1)
print("TODOS OK")
