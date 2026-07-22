#!/usr/bin/env python3
"""
test_totp.py — Pruebas del generador TOTP (RFC 6238) de la mejora D.

Usa los VECTORES DE PRUEBA OFICIALES del Apéndice B del RFC 6238 (semilla ASCII
"12345678901234567890" y variantes SHA-256/512), más la disciplina de secreto (la semilla solo
se lee desde loot/, nunca como literal). Sin pytest ni red.

    python tests/test_totp.py    (sale 1 si algo falla).
"""
import base64
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import totp as t  # noqa: E402

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


# Semillas del RFC 6238 App.B (ASCII -> base32). SHA1=20 bytes; SHA256=32; SHA512=64.
def b32(ascii_seed):
    return base64.b32encode(ascii_seed.encode()).decode()


SEED1 = "12345678901234567890"
SEED_SHA1 = b32(SEED1)                       # 20 bytes
SEED_SHA256 = b32((SEED1 * 2)[:32])          # 32 bytes: "12345678901234567890123456789012"
SEED_SHA512 = b32((SEED1 * 4)[:64])          # 64 bytes

# (tiempo, algo, semilla, código8) — tabla del RFC 6238 (digits=8, T0=0, X=30).
VECTORS = [
    (59,          "sha1",   SEED_SHA1,   "94287082"),
    (1111111109,  "sha1",   SEED_SHA1,   "07081804"),
    (1111111111,  "sha1",   SEED_SHA1,   "14050471"),
    (1234567890,  "sha1",   SEED_SHA1,   "89005924"),
    (2000000000,  "sha1",   SEED_SHA1,   "69279037"),
    (20000000000, "sha1",   SEED_SHA1,   "65353130"),
    (59,          "sha256", SEED_SHA256, "46119246"),
    (1234567890,  "sha256", SEED_SHA256, "91819424"),
    (59,          "sha512", SEED_SHA512, "90693936"),
    (20000000000, "sha512", SEED_SHA512, "47863826"),
]

for ts, algo, seed, expected in VECTORS:
    got = t.totp(seed, for_time=ts, digits=8, period=30, algo=algo)
    ok(got == expected, f"RFC6238 t={ts} {algo}: esperado {expected}, obtenido {got}")

# 6 dígitos (uso real de autenticadores): sufijo del código de 8.
ok(t.totp(SEED_SHA1, for_time=59, digits=6, period=30, algo="sha1") == "287082",
   "6 dígitos = sufijo del código de 8")

# Tolerancia de formato: minúsculas, espacios y padding omitido deben dar el mismo código.
noisy = SEED_SHA1.lower().rstrip("=")
noisy = " ".join(noisy[i:i + 4] for i in range(0, len(noisy), 4))
ok(t.totp(noisy, for_time=59, digits=8) == "94287082", "base32 con espacios/minúsculas/sin padding = mismo código")

# --- disciplina de secreto: read_seed exige loot/ (forma), confina por realpath y rechaza literal ---
try:
    t.read_seed("no/es/loot/semilla.txt")
    ok(False, "read_seed debe RECHAZAR una ref fuera de loot/")
except ValueError:
    ok(True, "read_seed rechaza ref fuera de loot/ (forma)")

# La semilla vive BAJO el repo (engagements/<id>/loot/) — el confinamiento realpath lo exige.
EID = "_totp_test"
loot = os.path.join(ROOT, "engagements", EID, "loot")
shutil.rmtree(os.path.join(ROOT, "engagements", EID), ignore_errors=True)
os.makedirs(loot)
try:
    ref = os.path.join("engagements", EID, "loot", "totp-userA.txt")
    with open(os.path.join(ROOT, ref), "w", encoding="utf-8") as f:
        f.write(SEED_SHA1 + "\n")
    ok(t.totp(t.read_seed(ref), for_time=59, digits=8) == "94287082",
       "read_seed lee la semilla de loot/ y genera bien")
    # (H2) ref con forma de loot/ pero que por traversal `..` escaparía => ValueError (confinamiento).
    try:
        t.read_seed(os.path.join("engagements", EID, "loot", "..", "..", "..", "..", "etc", "passwd"))
        ok(False, "read_seed debe RECHAZAR un traversal `..` fuera de loot/")
    except ValueError:
        ok(True, "read_seed confina por realpath: `..` fuera de loot/ => ValueError (H2)")
    # ref con forma de loot/ pero inexistente => FileNotFoundError (fail-closed).
    try:
        t.read_seed(os.path.join("engagements", EID, "loot", "no-existe.txt"))
        ok(False, "read_seed debe fallar si el fichero de loot/ no existe")
    except FileNotFoundError:
        ok(True, "read_seed falla (fail-closed) si la semilla de loot/ no existe")
finally:
    shutil.rmtree(os.path.join(ROOT, "engagements", EID), ignore_errors=True)

# La CLI nunca acepta la semilla como argumento (solo --secret-ref): confirma que no hay tal opción.
import argparse  # noqa: E402
ap_has_secret_literal = False
try:
    t.main(["--secret", SEED_SHA1])  # opción inexistente => argparse sale con SystemExit(2)
except SystemExit as e:
    ap_has_secret_literal = (e.code == 0)
ok(not ap_has_secret_literal, "la CLI NO acepta la semilla literal (--secret) — solo --secret-ref a loot/")

print(f"\n  RESUMEN test_totp:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
