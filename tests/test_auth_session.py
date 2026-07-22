#!/usr/bin/env python3
"""
test_auth_session.py — Pruebas de la mejora D (adquisición de sesión autenticada):
- el bloque `identities[].auth` del esquema (login_url/method requeridos, enums),
- las invariantes de seguridad de `tools/acquire_session.py` (scope fail-closed, refs solo a loot/),
- registro del agente `auth-recon` y su topología A2A bidireccional.

Sin pytest ni red. Usa jsonschema si está; si no, valida los invariantes clave a mano.

    python tests/test_auth_session.py    (sale 1 si algo falla).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


# === esquema: identities[].auth =============================================================
sch = json.load(open(os.path.join(ROOT, "contracts", "engagement.schema.json"), encoding="utf-8"))
auth = sch["properties"]["identities"]["items"]["properties"].get("auth")
ok(auth is not None, "schema: identities[].auth existe")
ok(auth and auth.get("required") == ["login_url", "method"], "schema: auth requiere login_url+method")
ap = (auth or {}).get("properties", {})
for f in ("login_url", "method", "credentials_ref", "totp_secret_ref", "steps", "session_type"):
    ok(f in ap, f"schema: auth.{f} presente")
ok("form" in ap.get("method", {}).get("enum", []), "schema: method enum incl. form")
ok(set(ap.get("session_type", {}).get("enum", [])) >= {"cookie", "bearer", "storage-state"},
   "schema: session_type enum cubre cookie/bearer/storage-state")
step_actions = ap.get("steps", {}).get("items", {}).get("properties", {}).get("action", {}).get("enum", [])
ok("totp" in step_actions and "fill" in step_actions, "schema: steps.action incl. totp/fill")

# 'auth' NO está en required de la identidad (retrocompatible).
ok("auth" not in sch["properties"]["identities"]["items"].get("required", []),
   "schema: auth NO es obligatorio (retrocompatible)")

# Validación con jsonschema si está disponible (no es dependencia dura).
try:
    import jsonschema  # noqa: E402
    base = {"engagement_id": "LAB", "scope_ref": "s", "phase": "recon", "targets": [], "findings": []}
    good = dict(base, identities=[{"identity_id": "userA", "role": "user", "auth": {
        "login_url": "https://app.lab.test/login", "method": "form",
        "credentials_ref": "engagements/LAB/loot/userA.txt"}}])
    jsonschema.validate(good, sch); ok(True, "jsonschema: identidad con auth válido valida")
    bad = dict(base, identities=[{"identity_id": "userA", "role": "user", "auth": {"method": "form"}}])
    try:
        jsonschema.validate(bad, sch); ok(False, "jsonschema: auth sin login_url debería fallar")
    except jsonschema.ValidationError:
        ok(True, "jsonschema: auth sin login_url RECHAZADO")
except ImportError:
    print("  [info] jsonschema no instalado — validación estructural por encima cubre los invariantes")

# === acquire_session: invariantes de seguridad =============================================
import acquire_session as acq  # noqa: E402

# _loot_path rechaza refs fuera de loot/ (fail-closed), sin tocar disco para la comprobación de forma.
try:
    acq._loot_path("/tmp/creds.txt", "credentials_ref"); ok(False, "_loot_path debe rechazar fuera de loot/")
except ValueError:
    ok(True, "_loot_path rechaza ref fuera de loot/")

# in_scope: fail-closed si no hay scope; y compara host contra in_scope.
ok(acq.in_scope("https://app.lab.test/login", None) is False, "in_scope: sin scope => False (fail-closed)")
scope = {"in_scope": {"domains": ["app.lab.test"], "ips": [], "cidrs": []}}
ok(acq.in_scope("https://app.lab.test/login", scope) is True, "in_scope: host en in_scope => True")
ok(acq.in_scope("https://accounts.google.com/o/oauth2", scope) is False,
   "in_scope: IdP de terceros fuera de scope => False (no improvisar alcance)")
# corrección council: in_scope debe fundir los hosts de in_scope.urls[] (paridad con scope_guard).
scope_urls = {"in_scope": {"urls": ["https://portal.acme.example/login"], "domains": [], "ips": [], "cidrs": []}}
ok(acq.in_scope("https://portal.acme.example/login", scope_urls) is True,
   "in_scope: host declarado SOLO vía in_scope.urls[] => True (no rompe engagements URL-scoped)")
# out_of_scope gana (paridad con scope_guard): un host en ambos => False.
scope_out = {"in_scope": {"domains": ["app.lab.test"]}, "out_of_scope": {"domains": ["app.lab.test"]}}
ok(acq.in_scope("https://app.lab.test/login", scope_out) is False,
   "in_scope: host también en out_of_scope => False (out_of_scope gana)")

# _loot_path confina por realpath: un traversal `..` con forma de loot/ => ValueError (H2).
try:
    acq._loot_path("engagements/x/loot/../../../../etc/passwd", "credentials_ref")
    ok(False, "_loot_path debe rechazar traversal `..` fuera de loot/")
except ValueError:
    ok(True, "_loot_path confina por realpath: `..` fuera de loot/ => ValueError (H2)")

# La CLI no acepta secretos por argumento (solo --identity/--engagement/--headful): ninguna
# add_argument declara un valor sensible (la mención a totp.py --secret-ref en la guía es texto, no opción).
acq_src = open(os.path.join(ROOT, "tools", "acquire_session.py"), encoding="utf-8").read()
ok('add_argument("--secret' not in acq_src and 'add_argument("--password' not in acq_src
   and 'add_argument("--totp' not in acq_src,
   "acquire_session: la CLI no declara ninguna opción de material sensible (nada por argv)")

# === agente auth-recon + topología A2A ======================================================
cards = json.load(open(os.path.join(ROOT, "contracts", "agent-cards.json"), encoding="utf-8"))["cards"]
by = {c["name"]: set(c.get("a2a_peers") or []) for c in cards}
ok("auth-recon" in by, "agent-cards: auth-recon registrado")
for peer in ("api-recon", "api-exploit", "web-exploit"):
    ok(peer in by.get("auth-recon", set()), f"a2a: auth-recon declara {peer}")
    ok("auth-recon" in by.get(peer, set()), f"a2a: {peer} declara auth-recon (bidireccional, C14)")

md = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
ok("auth-recon" in md and "totp" in md.lower(), "AGENTS.md: menciona auth-recon + TOTP en el flujo")

print(f"\n  RESUMEN test_auth_session:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
