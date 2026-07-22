#!/usr/bin/env python3
"""
test_secret_scan.py — Pruebas del guard C12 de secretos en el blackboard (OWASP LLM02).

Cubre la lógica PURA sin red ni pytest: los detectores de `tools/redactor.py`
(`scan`/`scan_client_auth`) y la decisión de bloqueo `secret_scan.blocking_reason`. La
integración del contrato del hook (stdin -> decision:block) la ejerce el dry-run.

Invariante central de una herramienta ofensiva: un secreto DESCUBIERTO del cliente es un
HALLAZGO legítimo (no se bloquea), pero un secreto del OPERADOR/motor y el material de auth
VIVO de las identidades de prueba (Bearer/Cookie) NO deben quedar en claro en el blackboard.

Ejecuta:  python tests/test_secret_scan.py   (sale 1 si algo falla).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))

import redactor  # noqa: E402
import secret_scan  # noqa: E402

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


# Material de ejemplo ----------------------------------------------------------------------
BEARER = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyQSJ9.Zm9vYmFyc2ln"
COOKIE = "Cookie: session=abcdef0123456789ABCDEF0123456789"
OP_KEY = "sk-ant-" + "A" * 32                       # secreto del OPERADOR (anthropic_key)
SECRET_REF = "engagements/LAB-2026-009/loot/userA-token.txt"   # referencia legítima (ruta)
DISCOVERED = 'hallazgo: hardcoded api_key="AKIA1234567890ABCDEF" en app.js'  # cliente => legítimo

# --- redactor.scan (operator_only) ---------------------------------------------------------
ok("anthropic_key" in redactor.scan(OP_KEY, operator_only=True),
   "scan(operator_only): detecta la API key de Anthropic del operador")
ok(redactor.scan(BEARER, operator_only=True) == [],
   "scan(operator_only): un Bearer de cliente NO es secreto del operador")

# --- redactor.scan_client_auth: bloquea SOLO la credencial VIVA ---------------------------
ok("bearer" in redactor.scan_client_auth(BEARER),
   "scan_client_auth: detecta Authorization: Bearer vivo")
ok("cookie" in redactor.scan_client_auth(COOKIE),
   "scan_client_auth: detecta Cookie de sesión viva")
ok(redactor.scan_client_auth(SECRET_REF) == [],
   "scan_client_auth: una ruta secret_ref NO casa (sin falso positivo)")
ok(redactor.scan_client_auth("El endpoint exige un Bearer token para autenticar") == [],
   "scan_client_auth: la MENCIÓN de 'Bearer token' (sin token de >=16) NO casa")
ok(redactor.scan_client_auth(DISCOVERED) == [],
   "scan_client_auth: un api_key DESCUBIERTO del cliente NO se marca (es hallazgo)")

# --- secret_scan.blocking_reason: la decisión del hook ------------------------------------
ok(secret_scan.blocking_reason("targets limpios, findings sin secretos") is None,
   "blocking_reason: blackboard limpio => None (no bloquea)")
ok(secret_scan.blocking_reason(SECRET_REF) is None,
   "blocking_reason: solo una referencia secret_ref => None (no bloquea)")
ok(secret_scan.blocking_reason(DISCOVERED) is None,
   "blocking_reason: credencial DESCUBIERTA del cliente => None (hallazgo legítimo, no se bloquea)")

r_op = secret_scan.blocking_reason("fuga: " + OP_KEY)
ok(r_op is not None and "OPERADOR" in r_op,
   "blocking_reason: secreto del operador => bloquea con motivo del operador")

r_cli = secret_scan.blocking_reason('evidence: "' + BEARER + '"')
ok(r_cli is not None and "identity_id" in r_cli and "secret_ref" in r_cli,
   "blocking_reason: Bearer vivo => bloquea y guía a referenciar por secret_ref/identity_id")

r_both = secret_scan.blocking_reason(OP_KEY + "\n" + COOKIE)
ok(r_both is not None and "OPERADOR" in r_both and "AUTENTICACIÓN" in r_both,
   "blocking_reason: operador + cliente vivo => un único motivo que cita ambas clases")

# --- CONTRATO CONSCIENTE (cobertura documentada, NO exhaustiva) -----------------------------
# El gate caza la PRESENTACIÓN en vivo (Authorization: Bearer / Cookie:). Un token/JWT PELADO como
# valor suelto escapa A PROPÓSITO: distinguir el JWT de una identidad de prueba del JWT DESCUBIERTO del
# cliente (hallazgo legítimo) exigiría contexto que un regex no tiene. El arnés DEBE serializar el material
# como cabecera (lo imponen los prompts) y la redacción de prompt es el control primario; esto lo fija como
# contrato consciente. (Blast radius acotado: contracts/engagement.json está gitignored — no se pushea.)
BARE_JWT = '{"session_token":"eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyQSJ9.Zm9vYmFyc2lnbmF0dXJl"}'
ok(secret_scan.blocking_reason(BARE_JWT) is None,
   "contrato: un JWT PELADO (sin Bearer/Cookie) NO se bloquea — el arnés debe serializar auth como cabecera")

# --- identity_auth_reason: disciplina de referencia del bloque auth (mejora D) --------------
import json as _json  # noqa: E402

# Bloque auth LIMPIO: todo por *_ref a loot/, steps con marcadores no sensibles => no bloquea.
AUTH_OK = _json.dumps({"identities": [{"identity_id": "userA", "role": "user", "auth": {
    "login_url": "https://app.lab.test/login", "method": "form",
    "credentials_ref": "engagements/LAB-2026-009/loot/userA-creds.txt",
    "totp_secret_ref": "engagements/LAB-2026-009/loot/userA-totp.txt",
    "steps": [{"action": "fill", "selector": "#user", "value": "{{user}}"},
              {"action": "fill", "selector": "#pass", "value": "{{pass}}"},
              {"action": "totp", "selector": "#otp"}]}}]})
ok(secret_scan.identity_auth_reason(AUTH_OK) is None,
   "identity_auth: bloque auth con *_ref a loot/ y marcadores => no bloquea")

# credentials_ref pegado en claro (no es ref a loot/) => bloquea.
AUTH_BADREF = _json.dumps({"identities": [{"identity_id": "userA", "role": "user", "auth": {
    "login_url": "https://app.lab.test/login", "method": "form",
    "credentials_ref": "userA:Sup3rSecret!"}}]})
r_badref = secret_scan.identity_auth_reason(AUTH_BADREF)
ok(r_badref is not None and "credentials_ref" in r_badref,
   "identity_auth: credentials_ref que no es ref a loot/ => bloquea")

# semilla TOTP pegada como value en un step => bloquea (secreto en claro).
AUTH_SEEDVAL = _json.dumps({"identities": [{"identity_id": "userA", "role": "user", "auth": {
    "login_url": "https://app.lab.test/login", "method": "form",
    "steps": [{"action": "fill", "selector": "#otp", "value": OP_KEY}]}}]})
ok(secret_scan.identity_auth_reason(AUTH_SEEDVAL) is not None,
   "identity_auth: secreto pegado en steps[].value => bloquea")

# value_ref que no apunta a loot/ => bloquea.
AUTH_BADVR = _json.dumps({"identities": [{"identity_id": "userA", "role": "user", "auth": {
    "login_url": "https://app.lab.test/login", "method": "form",
    "steps": [{"action": "fill", "selector": "#pass", "value_ref": "/tmp/pass.txt"}]}}]})
ok(secret_scan.identity_auth_reason(AUTH_BADVR) is not None,
   "identity_auth: steps[].value_ref fuera de loot/ => bloquea")

# identidad SIN bloque auth (retrocompatible) => no bloquea.
ok(secret_scan.identity_auth_reason(_json.dumps({"identities": [{"identity_id": "anon", "role": "anon"}]})) is None,
   "identity_auth: identidad sin bloque auth => no bloquea (retrocompatible)")

# --- FAIL-OPEN: ante un fallo del detector EN RUNTIME, jamás bloquea (devuelve None) --------
def _boom(*_a, **_k):
    raise RuntimeError("detector runtime fail")


_orig = redactor.scan_client_auth
redactor.scan_client_auth = _boom
try:
    ok(secret_scan.blocking_reason(BEARER) is None,
       "fail-open: si un detector lanza en RUNTIME, blocking_reason devuelve None (no rompe el flujo)")
finally:
    redactor.scan_client_auth = _orig

print(f"\n  RESUMEN test_secret_scan:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
