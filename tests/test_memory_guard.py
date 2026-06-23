#!/usr/bin/env python3
"""
test_memory_guard.py — Pruebas del guard de sanitización de la memoria de aprendizaje.

Cubre la lógica pura (is_memory_path / extract_new_text / find_violations) sin necesidad de
pytest ni de red. Ejecuta:  python tests/test_memory_guard.py   (sale 1 si algo falla).
La integración del contrato del hook (stdin -> permissionDecision=deny) se prueba aparte por stdin.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))

import memory_guard as mg  # noqa: E402

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


# Scope de prueba (no toca disco; se pasa directo a find_violations).
SCOPE = {
    "in_scope": {"ips": ["10.10.10.5"], "cidrs": ["10.10.10.0/24"], "domains": ["acme-corp.test"]},
    "out_of_scope": {"ips": ["10.10.10.250"], "domains": ["nope.acme-corp.test"]},
}

# --- is_memory_path -------------------------------------------------------------------------
ok(mg.is_memory_path(os.path.join(ROOT, ".claude", "agent-memory", "web-exploit", "MEMORY.md")),
   "is_memory_path: project memory debe coincidir")
ok(mg.is_memory_path(os.path.join(ROOT, ".claude", "agent-memory-local", "sqlmap", "MEMORY.md")),
   "is_memory_path: local memory debe coincidir")
ok(not mg.is_memory_path(os.path.join(ROOT, "README.md")),
   "is_memory_path: un fichero normal NO debe coincidir")
ok(not mg.is_memory_path(os.path.join(ROOT, "contracts", "engagement.json")),
   "is_memory_path: el blackboard NO debe coincidir")
ok(not mg.is_memory_path(""), "is_memory_path: vacío => False")

# --- extract_new_text -----------------------------------------------------------------------
ok(mg.extract_new_text("Write", {"content": "abc"}) == "abc", "extract: Write usa content")
ok(mg.extract_new_text("Edit", {"old_string": "x", "new_string": "y"}) == "y", "extract: Edit usa new_string")
ok("a" in mg.extract_new_text("MultiEdit", {"edits": [{"new_string": "a"}, {"new_string": "b"}]})
   and "b" in mg.extract_new_text("MultiEdit", {"edits": [{"new_string": "a"}, {"new_string": "b"}]}),
   "extract: MultiEdit concatena new_string")

# --- find_violations: contenido LIMPIO (debe permitirse) ------------------------------------
clean = ("Privesc Linux: si sudo permite find, usa GTFOBins (sudo find . -exec /bin/sh once). "
         "Si el WAF bloquea UNION en SQLi, prueba encoding mixto y comentarios inline. "
         "Rango de laboratorio 10.0.0.0/8 y loopback 127.0.0.1 son ejemplos.")
ok(mg.find_violations(clean, SCOPE) == [], "find: técnica generalizada limpia => sin violaciones")
ok(mg.find_violations("", SCOPE) == [], "find: texto vacío => sin violaciones")

# --- find_violations: SECRETOS --------------------------------------------------------------
ok(any(v.startswith("secreto:anthropic_key") for v in
       mg.find_violations("clave del bot sk-ant-" + "A" * 30, SCOPE)),
   "find: detecta API key de Anthropic")
ok(any(v.startswith("secreto:private_key") for v in
       mg.find_violations("-----BEGIN OPENSSH PRIVATE KEY-----\nabc", SCOPE)),
   "find: detecta clave privada")

# --- find_violations: IDENTIFICADORES DEL SCOPE ---------------------------------------------
ok("ip_scope:10.10.10.5" in mg.find_violations("El objetivo 10.10.10.5 cayó con MS17-010", SCOPE),
   "find: IP del scope (privada) se bloquea como ip_scope")
ok(any(v == "dominio_scope:acme-corp.test" for v in
       mg.find_violations("Subdominio interesante en acme-corp.test", SCOPE)),
   "find: dominio del scope se bloquea")
ok("ip_scope:10.10.10.250" in mg.find_violations("y 10.10.10.250 (out) tambien", SCOPE),
   "find: IP out_of_scope tambien se bloquea")

# --- find_violations: IPs PÚBLICAS vs PRIVADAS/DOC ------------------------------------------
ok("ip_publica:8.8.8.8" in mg.find_violations("apunta a 8.8.8.8 para exfil", SCOPE),
   "find: IP pública enrutable se bloquea")
ok(mg.find_violations("usa 192.168.1.10 en el lab", SCOPE) == [],
   "find: IP privada NO del scope se permite")
ok(mg.find_violations("doc range 192.0.2.50 y 203.0.113.7", SCOPE) == [],
   "find: rangos de documentación se permiten")

# --- find_violations: LOOT ------------------------------------------------------------------
ok(any(v == "loot:ntlm_pair" for v in
       mg.find_violations("Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::", SCOPE)),
   "find: par NTLM (secretsdump) se bloquea como loot")
ok(any(v == "loot:unix_hash" for v in
       mg.find_violations("root:$6$abcd1234$EfGhIjKlMnOpQrStUvWx:18000:0:99999:7:::", SCOPE)),
   "find: hash de /etc/shadow se bloquea como loot")

print(f"\n  RESUMEN test_memory_guard:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
