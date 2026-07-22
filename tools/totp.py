#!/usr/bin/env python3
"""
totp.py — Generador de códigos TOTP (RFC 6238) para el login de 2FA de una identidad de prueba
(mejora D: adquisición de sesión autenticada). Solo stdlib.

DISCIPLINA DE SECRETO (CONSTITUTION §1/§6, control C12): la semilla TOTP es material sensible de
CLIENTE (zona E3). Este script la lee **SOLO desde un fichero bajo `engagements/<id>/loot/`** (la
zona de material crudo, fuera de git) — NUNCA la acepta como argumento de línea de comandos: un
secreto en `argv` se filtraría a `ps`, al historial del shell y a los logs. Emite únicamente el
código de 6-8 dígitos por stdout; nunca la semilla.

Uso:
    python tools/totp.py --secret-ref engagements/<id>/loot/totp-userA.txt [--digits 6] [--period 30] [--algo sha1]
El fichero debe contener la semilla en base32 (formato estándar de los autenticadores; se ignoran
espacios y se tolera el padding). Sale 0 e imprime el código; sale != 0 con un motivo en stderr.

Función pura `totp(secret_b32, for_time, ...)` — testeable con los vectores oficiales del RFC 6238
(tests/test_totp.py).
"""
import argparse
import base64
import hashlib
import hmac
import os
import re
import struct
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    from redactor import is_loot_ref
except Exception:  # noqa: BLE001 — fallback autónomo si redactor no está a mano
    _LR = re.compile(r"(^|/)engagements/[^/]+/loot/")
    def is_loot_ref(ref):  # type: ignore
        return isinstance(ref, str) and bool(_LR.search(ref.replace("\\", "/")))

_ALGOS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


def totp(secret_b32, for_time=None, digits=6, period=30, algo="sha1", t0=0):
    """Código TOTP (RFC 6238) para `for_time` (epoch seg; def. ahora). Función pura.

    `secret_b32`: semilla en base32 (RFC 4648, mayúsculas; se tolera minúsculas/espacios/padding)."""
    if for_time is None:
        for_time = time.time()
    key = _b32decode(secret_b32)
    counter = int((for_time - t0) // period)
    return _hotp(key, counter, digits, algo)


def _b32decode(secret_b32):
    s = re.sub(r"\s+", "", secret_b32).upper()
    s += "=" * ((8 - len(s) % 8) % 8)  # repone el padding que los autenticadores suelen omitir
    return base64.b32decode(s, casefold=True)


def _hotp(key, counter, digits, algo):
    """HOTP (RFC 4226) sobre `counter`, base del TOTP."""
    h = hmac.new(key, struct.pack(">Q", counter), _ALGOS[algo]).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def read_seed(secret_ref):
    """Lee la semilla desde un fichero BAJO `engagements/<id>/loot/`. Fail-closed si la ref no tiene la
    forma de loot/, si su ruta REAL escapa de `engagements/*/loot/` (traversal `..`/symlink), o si no
    existe — nunca se acepta una semilla literal. La confinación por realpath cierra el vector de
    lectura de fichero arbitrario que el chequeo de forma por sí solo no impide."""
    if not is_loot_ref(secret_ref):
        raise ValueError(f"--secret-ref debe apuntar a engagements/<id>/loot/ (E3), no a '{secret_ref}'")
    path = secret_ref if os.path.isabs(secret_ref) else os.path.join(ROOT, secret_ref)
    real = os.path.realpath(path).replace("\\", "/")
    eng_root = os.path.realpath(os.path.join(ROOT, "engagements")).replace("\\", "/")
    # Real debe colgar de engagements/<algo>/loot/ dentro del repo (no `..` fuera, no otro sitio).
    if not (real.startswith(eng_root + "/") and re.search(r"/engagements/[^/]+/loot/", real)):
        raise ValueError(f"la semilla resuelve FUERA de engagements/<id>/loot/ (traversal/symlink): {secret_ref}")
    if not os.path.isfile(real):
        raise FileNotFoundError(f"no existe el fichero de semilla: {secret_ref}")
    with open(real, "r", encoding="utf-8", errors="strict") as f:
        seed = f.read().strip()
    if not seed:
        raise ValueError(f"el fichero de semilla está vacío: {secret_ref}")
    return seed


_read_seed = read_seed  # alias interno (compat)


def main(argv=None):
    # allow_abbrev=False: evita que `--secret <literal>` se acepte como prefijo de `--secret-ref`
    # (la semilla NUNCA por argumento; _read_seed además exige loot/ como segunda barrera).
    ap = argparse.ArgumentParser(description="Genera un código TOTP (RFC 6238) leyendo la semilla desde loot/.",
                                 allow_abbrev=False)
    ap.add_argument("--secret-ref", required=True,
                    help="Ruta al fichero con la semilla base32, bajo engagements/<id>/loot/ (NUNCA la semilla literal).")
    ap.add_argument("--digits", type=int, default=6, choices=(6, 7, 8))
    ap.add_argument("--period", type=int, default=30)
    ap.add_argument("--algo", default="sha1", choices=tuple(_ALGOS))
    args = ap.parse_args(argv)
    try:
        seed = read_seed(args.secret_ref)
        print(totp(seed, digits=args.digits, period=args.period, algo=args.algo))
    except Exception as e:  # noqa: BLE001 — mensaje accionable, sin volcar la semilla
        print(f"totp: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
