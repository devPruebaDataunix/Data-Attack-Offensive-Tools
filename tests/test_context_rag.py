#!/usr/bin/env python3
"""
test_context_rag.py — Pruebas del AISLAMIENTO del RAG de contexto per-engagement (CONSTITUTION §1).

Cubre la lógica pura de rutas (context_paths.py) SIN torch/embeddings: es la parte crítica de
seguridad (un engagement jamás debe poder leer/escribir el store de otro, ni salir de engagements/).
El poblado/consulta con embeddings se verifica en Kali (como la Capa 2 del RAG de conocimiento).

Ejecuta:  python tests/test_context_rag.py   (sale 1 si algo falla).
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rag", "context"))

import context_paths as cp  # noqa: E402

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


def raises(fn, msg):
    try:
        fn()
        ok(False, msg + " (NO lanzó)")
    except ValueError:
        ok(True, msg)
    except Exception as e:  # noqa: BLE001
        ok(False, f"{msg} (lanzó {type(e).__name__}, esperaba ValueError)")


# --- context_db_path: id válido -> bajo engagements/<id>/context.db -------------------------
d = tempfile.mkdtemp()
p = cp.context_db_path(d, "LAB-2026-009", create=True)
expected = os.path.join(os.path.realpath(d), "engagements", "LAB-2026-009", "context.db")
ok(os.path.realpath(p) == expected, "context_db_path: id válido resuelve bajo engagements/<id>/context.db")
ok(os.path.isdir(os.path.dirname(p)), "context_db_path(create=True): crea el directorio del engagement")

# --- AISLAMIENTO: rechaza ids que sean rutas / traversal / vacíos ---------------------------
raises(lambda: cp.context_db_path(d, ""), "rechaza engagement_id vacío")
raises(lambda: cp.context_db_path(d, "."), "rechaza '.'")
raises(lambda: cp.context_db_path(d, ".."), "rechaza '..' (traversal)")
raises(lambda: cp.context_db_path(d, "../../etc"), "rechaza traversal con separadores")
raises(lambda: cp.context_db_path(d, "a/b"), "rechaza separador '/' (un id no es una ruta)")
raises(lambda: cp.context_db_path(d, "a\\b"), "rechaza separador '\\\\'")
raises(lambda: cp.context_db_path(d, "x\0y"), "rechaza byte nulo")

# Dos engagements distintos -> dos stores DISTINTOS (nunca comparten fichero).
pa = cp.context_db_path(d, "ENG-A")
pb = cp.context_db_path(d, "ENG-B")
ok(pa != pb and os.path.dirname(pa) != os.path.dirname(pb),
   "aislamiento: engagements distintos => stores en directorios distintos")

# El store JAMÁS cae en rag/knowledge (la zona del RAG de conocimiento general).
ok("rag" + os.sep + "knowledge" not in os.path.realpath(pa),
   "aislamiento: el store de contexto NO vive en rag/knowledge")

# --- iter_indexable_files: indexa recon/evidence/notes, NUNCA loot/ -------------------------
base = cp.engagement_dir(d, "LAB-2026-009", create=True)
for sub in ("recon", "evidence", "notes", "loot", "exploit"):
    os.makedirs(os.path.join(base, sub), exist_ok=True)
open(os.path.join(base, "recon", "nmap.txt"), "w").write("22/tcp open ssh")
open(os.path.join(base, "evidence", "bola.md"), "w").write("# BOLA\nuserB accedió al objeto de A")
open(os.path.join(base, "notes", "ideas.md"), "w").write("probar mass assignment en /users")
open(os.path.join(base, "loot", "userA-token.txt"), "w").write("eyJhbGciOiJIUzI1NiJ9.secret.sig")  # NO indexar
open(os.path.join(base, "recon", "screenshot.png"), "w").write("binario")  # ext no indexable
found = list(cp.iter_indexable_files(d, "LAB-2026-009"))
paths = [os.path.basename(f) for _, f in found]
ok("nmap.txt" in paths and "bola.md" in paths and "ideas.md" in paths,
   "iter: indexa recon/evidence/notes de texto")
ok("userA-token.txt" not in paths, "iter: NUNCA indexa loot/ (material crudo de cliente)")
ok("screenshot.png" not in paths, "iter: ignora extensiones no-texto")
ok(all(sub in cp.INDEXABLE_SUBDIRS for sub, _ in found), "iter: solo subdirs indexables")

# --- AISLAMIENTO: casos límite adicionales (hardening del council) --------------------------
raises(lambda: cp.context_db_path(d, "/etc/passwd"), "rechaza una ruta absoluta POSIX como id")
raises(lambda: cp.context_db_path(d, "C:\\Windows"), "rechaza una ruta absoluta Windows como id")
raises(lambda: cp.context_db_path(d, "D:x"), "rechaza ':' (drive-relative / ADS de Windows)")
# '...' (solo puntos, no '.'/'..'): SIEMPRE seguro — o queda EN-ZONA (POSIX, dir literal) o se rechaza
# (Windows colapsa los puntos finales al padre y el guard eng_dir==root lo corta). Nunca escapa la zona.
engs_root = os.path.realpath(os.path.join(d, "engagements"))
try:
    p3 = cp.context_db_path(d, "...")
    ok(os.path.commonpath([engs_root, os.path.realpath(p3)]) == engs_root and os.path.realpath(p3) != engs_root,
       "'...' queda en-zona (dir literal, POSIX)")
except ValueError:
    ok(True, "'...' se rechaza (Windows colapsa puntos finales) — también seguro")

# loot/ ANIDADO (recon/loot/…) también se excluye (poda de dirnames en el os.walk).
os.makedirs(os.path.join(base, "recon", "loot"), exist_ok=True)
open(os.path.join(base, "recon", "loot", "creds.txt"), "w").write("secret")
nested = [os.path.basename(f) for _, f in cp.iter_indexable_files(d, "LAB-2026-009")]
ok("creds.txt" not in nested, "iter: excluye loot/ ANIDADO (recon/loot/…), no solo el de primer nivel")

# Symlink como directorio de engagement: prohibido (cierra el cruce intra-zona ENG-A -> ENG-B).
# En Windows crear symlinks exige privilegio: si no se puede, se OMITE (no falla el test).
try:
    engs = os.path.join(d, "engagements")
    os.makedirs(os.path.join(engs, "ENG-REAL"), exist_ok=True)
    link = os.path.join(engs, "ENG-LINK")
    if not os.path.exists(link):
        os.symlink(os.path.join(engs, "ENG-REAL"), link, target_is_directory=True)
    raises(lambda: cp.context_db_path(d, "ENG-LINK"),
           "rechaza un directorio de engagement que sea symlink (anti cruce intra-zona)")
except (OSError, NotImplementedError):
    print("  [omitido] symlink no soportado en este entorno (Windows sin privilegio) — OK")

print(f"\n  RESUMEN test_context_rag:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
