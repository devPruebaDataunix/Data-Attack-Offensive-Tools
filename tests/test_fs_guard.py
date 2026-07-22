#!/usr/bin/env python3
"""
test_fs_guard.py — Pruebas del guard de confinamiento de lecturas (Read/Grep/Glob) de la mejora C.

Cubre la lógica pura (candidate_paths / violation), las ramas críticas de escape mediante `realpath`
PARCHEADO (cross-plataforma: no dependen de crear symlinks reales) y el contrato del hook (stdin ->
deny). Además, si el SO permite symlinks REALES, ejercita esos caminos de verdad; si no (Windows sin
privilegio), esos casos se OMITEN (no cuentan como fallo) — corren en POSIX/Kali.

    python tests/test_fs_guard.py    (sale 1 si algo falla).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))

import fs_guard as fg  # noqa: E402

PASS, FAIL, SKIP = 0, 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


def skip(msg):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {msg}")


EID = "_fsguard_test"
SRC = os.path.join(ROOT, "engagements", EID, "recon", "src")
LOOT = os.path.join(ROOT, "engagements", EID, "loot")


def rel(*parts):
    return os.path.join("engagements", EID, "recon", "src", *parts)


def cleanup():
    shutil.rmtree(os.path.join(ROOT, "engagements", EID), ignore_errors=True)


def can_symlink(target, link):
    try:
        os.symlink(target, link)
        return True
    except (OSError, NotImplementedError):
        return False


cleanup()
os.makedirs(os.path.join(SRC, "app"), exist_ok=True)
os.makedirs(LOOT, exist_ok=True)
with open(os.path.join(SRC, "app", "db.ts"), "w", encoding="utf-8") as f:
    f.write("// código de cliente inerte\n")
with open(os.path.join(LOOT, "creds.txt"), "w", encoding="utf-8") as f:
    f.write("secreto de otro sitio\n")

try:
    # --- candidate_paths ---------------------------------------------------------------------
    ok(fg.candidate_paths("Read", {"file_path": "a/b.ts"}) == ["a/b.ts"], "candidate: Read usa file_path")
    ok(fg.candidate_paths("Grep", {"path": "src", "pattern": "x"}) == ["src"], "candidate: Grep usa path")
    ok(fg.candidate_paths("Glob", {"pattern": "**/*.ts"}) == [], "candidate: Glob sin path => nada")
    ok(fg.candidate_paths("Read", {}) == [], "candidate: Read sin file_path => nada")
    ok(fg.candidate_paths("Read", {"file_path": None}) == [], "candidate: file_path None => nada")

    # --- under(): sin bug de prefijo ---------------------------------------------------------
    ok(fg.under("/a/b", "/a/b") and fg.under("/a/b/c", "/a/b"), "under: igual y descendiente => True")
    ok(not fg.under("/a/bc", "/a/b"), "under: /a/bc NO cuelga de /a/b (sin bug de prefijo)")

    # --- violation: LECTURAS LEGÍTIMAS (deben permitirse) ------------------------------------
    ok(fg.violation(rel("app", "db.ts")) is None, "violation: fichero real dentro de src => permitido")
    ok(fg.violation("AGENTS.md") is None, "violation: fichero normal del repo => permitido")
    ok(fg.violation("contracts/scope.example.json") is None, "violation: contrato del repo => permitido")
    ok(fg.violation(os.path.join("engagements", EID, "loot", "creds.txt")) is None,
       "violation: loot del MISMO engagement (fuera de src) => permitido")
    ok(fg.violation("") is None, "violation: vacío => permitido")

    # --- violation: TRAVERSAL `..` fuera del código de cliente (debe bloquear) ----------------
    r = fg.violation(rel("..", "..", "..", "loot", "creds.txt"))  # src/../../../loot/creds.txt
    ok(r is not None and "traversal" in r, "violation: `..` que sale de src/ hacia loot => bloqueo")
    ok(fg.violation(rel("..", "..", "..", "..", "..", "..", "etc", "passwd")) is not None,
       "violation: `..` profundo fuera del repo => bloqueo")

    # --- violation: fuera-de-repo absoluto SIN symlink (NO es asunto del guard, salvo ~/.claude) --
    ok(fg.violation("/etc/passwd") is None,
       "violation: lectura absoluta del host (no dato de cliente, no ~/.claude) => no se gatea aquí")

    # === Ramas críticas vía realpath PARCHEADO (cross-plataforma) ============================
    _orig_realpath = os.path.realpath
    ROOTfs = ROOT.replace("\\", "/")

    def patched(mapping):
        """Devuelve un realpath que sustituye por subcadena según `mapping` (needle -> destino).
        Emula que realpath colapsa `/./` y `//` (y resuelve el symlink mapeado)."""
        def _rp(p):
            pn = re.sub(r"/(?:\./)+", "/", re.sub(r"/+", "/", p.replace("\\", "/")))
            for needle, dest in mapping.items():
                if needle in pn:
                    return dest
            return _orig_realpath(p)
        return _rp

    # (crown jewel) destino real bajo ~/.claude, por RUTA ABSOLUTA DIRECTA (sin symlink) => bloqueo.
    if fg.HOME_CLAUDE:
        home_native = fg.HOME_CLAUDE  # ya normcase + '/'
        # Simula un file_path absoluto que YA es ~/.claude/.credentials.json (real == él mismo).
        cred = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
        rC = fg.violation(cred)
        ok(rC is not None and ".claude" in rC, "violation: lectura directa de ~/.claude => bloqueo (crown jewel)")
    else:
        skip("HOME_CLAUDE no resoluble en este entorno")

    # (H1) ANCLA `recon/src` symlinkeada FUERA del repo (a ~/.claude) => bloqueo, no debe pasar a (B).
    os.path.realpath = patched({f"engagements/{EID}/recon/src": "/root/.claude"})
    try:
        rH1 = fg.violation(rel("config.json"))  # recon/src/config.json con src -> /root/.claude
        ok(rH1 is not None and ("ancla" in rH1 or ".claude" in rH1),
           "violation: ancla recon/src symlinkeada a ~/.claude => bloqueo (H1 crítico)")
    finally:
        os.path.realpath = _orig_realpath

    # (H3) evasión del ancla con `/./`: debe seguir detectando el ancla y bloquear el cross-engagement.
    os.path.realpath = patched({"recon/src/leak": ROOTfs + f"/engagements/OTRO/loot/x"})
    try:
        rH3 = fg.violation(f"engagements/{EID}/recon/./src/leak")  # /./ intenta evadir el ancla
        ok(rH3 is not None and "symlink" in rH3,
           "violation: evasión de ancla con /./ + symlink a otro engagement => bloqueo (H3)")
    finally:
        os.path.realpath = _orig_realpath

    # (B) symlink del repo (fuera de src) que resuelve a ~/.claude ya lo cubre crown-jewel; verifica
    # además un escape del repo a un destino cualquiera fuera (no ~/.claude) por la rama (B).
    os.path.realpath = patched({f"engagements/{EID}/escape": "/mnt/otro-disco/x"})
    try:
        rB = fg.violation(os.path.join("engagements", EID, "escape"))
        ok(rB is not None and "FUERA del árbol del proyecto" in rB,
           "violation: symlink del repo que escapa a un destino externo => bloqueo (B)")
    finally:
        os.path.realpath = _orig_realpath

    # === Symlinks REALES (si el SO los permite; si no, SKIP — corren en POSIX/Kali) ===========
    link_c = os.path.join(SRC, "leak_loot")
    if can_symlink(os.path.join(ROOT, "engagements", EID, "loot"), link_c):
        ok(fg.violation(rel("leak_loot", "creds.txt")) is not None,
           "violation[real]: symlink de src/ hacia loot => bloqueo (C)")
        ok(fg.violation(rel("leak_loot")) is not None,
           "violation[real]: el propio symlink de src/ que sale => bloqueo (C)")
    else:
        skip("symlink real (C) src->loot no creable en este SO/privilegio")

    ext_target = tempfile.mkdtemp(prefix="fsguard_ext_")   # target EXTERNO en el tmpdir del sistema
    link_b = os.path.join(ROOT, "engagements", EID, "escape_link")
    if can_symlink(ext_target, link_b):
        ok(fg.violation(os.path.join("engagements", EID, "escape_link")) is not None,
           "violation[real]: symlink del repo que escapa del repo => bloqueo (B)")
    else:
        skip("symlink real (B) repo->fuera no creable en este SO/privilegio")
    shutil.rmtree(ext_target, ignore_errors=True)

    # --- contrato del hook por stdin (deny real) ----------------------------------------------
    hook = os.path.join(ROOT, ".claude", "hooks", "fs_guard.py")
    ev = {"tool_name": "Read", "tool_input": {"file_path": rel("..", "..", "..", "loot", "creds.txt")}}
    p = subprocess.run([sys.executable, hook], input=json.dumps(ev), capture_output=True, text=True)
    try:
        denied = json.loads(p.stdout).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    except Exception:
        denied = False
    ok(denied, "hook: stdin con traversal fuera de src => emite permissionDecision=deny")

    ev_ok = {"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}}
    p2 = subprocess.run([sys.executable, hook], input=json.dumps(ev_ok), capture_output=True, text=True)
    ok(p2.stdout.strip() == "", "hook: lectura legítima => sin salida (permitido)")

    ev_other = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    p3 = subprocess.run([sys.executable, hook], input=json.dumps(ev_other), capture_output=True, text=True)
    ok(p3.stdout.strip() == "", "hook: herramienta no-lectura (Bash) => no interfiere")
finally:
    cleanup()

print(f"\n  RESUMEN test_fs_guard:  {PASS} OK   {FAIL} fallos   {SKIP} omitidos")
sys.exit(1 if FAIL else 0)
