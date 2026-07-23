#!/usr/bin/env python3
"""
acquire_session.py — Driver de ADQUISICIÓN de sesión autenticada (mejora D). Autentica una identidad
de prueba (login web con Playwright + TOTP) y deposita la sesión adquirida en loot/, para que
`api-exploit`/`web-exploit` prueben authz DIFERENCIAL sin que el operador tenga que loguearse a mano.

Invariantes de seguridad (CONSTITUTION §1/§6 · scope §1 · secretos C12):
- **Scope, fail-closed.** El `login_url` del bloque `identities[].auth` DEBE estar en scope
  (`scope.json`); si no, se ABORTA. Reusa los verificadores deterministas de `scope_guard.py`.
- **Material solo desde/hacia loot/.** Usuario/contraseña (`credentials_ref`) y semilla TOTP
  (`totp_secret_ref`) se leen SOLO de `engagements/<id>/loot/`; la sesión adquirida (cookies /
  storage-state) se escribe SOLO en `engagements/<id>/loot/session-<identity>.json`. NUNCA se
  imprime el material ni se vuelca al blackboard: por stdout solo va el `secret_ref` (la RUTA) a fijar.
- **Sin secretos en argv.** Nada de credenciales/semilla por línea de comandos (se filtrarían a `ps`).
- **Anillo efímero (mejora C).** Este driver maneja un navegador contra contenido de cliente: su
  sitio es el contenedor efímero por-engagement (`deploy/engagement-run.sh`), no el host desnudo.

Si Playwright no está instalado, imprime la GUÍA operator-assisted (login manual + volcado del
storage-state a loot/) y sale != 0 — sin romper nada.

Uso:
    python tools/acquire_session.py --identity userA [--engagement <id>] [--headful]
Lee el bloque `auth` de esa identidad desde `contracts/engagement.json`.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")

sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from redactor import is_loot_ref  # dialecto único de refs a loot/ (compartido)
from urllib.parse import urlsplit
try:
    from scope_guard import load_scope, domain_in_list, ip_in_scope, URL_RE, IP_RE
except Exception:  # noqa: BLE001
    load_scope = None


def _err(msg):
    print(f"acquire_session: {msg}", file=sys.stderr)


def _host_of(url):
    """Host RFC-correcto de una URL (o host suelto): DESCARTA el userinfo (`user:pass@`), baja a
    minúsculas y soporta IPv6/puerto. Debe COINCIDIR con el host al que realmente conectan
    http.client/Playwright — un parseo ingenuo que pare en el primer `:` deja pasar
    `http://scope.example:x@evil.com/` como en-scope y luego conecta a evil.com (bypass de scope)."""
    try:
        h = urlsplit(url if "://" in str(url) else "http://" + str(url)).hostname
    except ValueError:
        return ""
    return (h or "").strip("[]").lower()


def in_scope(login_url, scope):
    """True si el host de `login_url` está en in_scope y NO en out_of_scope. Fail-closed (False) sin
    scope. Replica la semántica de `scope_guard`: funde los hosts de `in_scope.urls[]` en los dominios
    y deniega primero por `out_of_scope` (paridad con el gate determinista)."""
    if not scope or load_scope is None:
        return False
    host = _host_of(login_url)
    ins = scope.get("in_scope", {}) or {}
    out = scope.get("out_of_scope", {}) or {}

    def url_hosts(sec):
        return [_host_of(u) for u in (sec.get("urls", []) or []) if URL_RE and URL_RE.match(u)]

    is_ip = bool(IP_RE and IP_RE.match(host))
    # out_of_scope gana (como scope_guard).
    if is_ip and ip_in_scope(host, out.get("ips", []) or [], out.get("cidrs", []) or []):
        return False
    if not is_ip and domain_in_list(host, (out.get("domains", []) or []) + url_hosts(out)):
        return False
    # in_scope.
    if is_ip:
        return ip_in_scope(host, ins.get("ips", []) or [], ins.get("cidrs", []) or [])
    return domain_in_list(host, (ins.get("domains", []) or []) + url_hosts(ins))


def load_identity(identity_id):
    with open(ENGAGEMENT, "r", encoding="utf-8") as f:
        eng = json.load(f)
    for idt in (eng.get("identities") or []):
        if idt.get("identity_id") == identity_id:
            return eng, idt
    raise KeyError(f"identidad '{identity_id}' no está en identities[] del blackboard")


def _loot_path(ref, label, eid=None):
    """Resuelve una *_ref que DEBE ser de loot/ y existir (fail-closed). Confina por REALPATH a
    `engagements/<eid>/loot/` (o a cualquier `engagements/*/loot/` si no se da eid): rechaza el
    traversal `..`/symlink que escaparía a lectura de fichero arbitrario o al loot de OTRO engagement."""
    if not is_loot_ref(ref):
        raise ValueError(f"{label} debe apuntar a engagements/<id>/loot/ (E3), no a '{ref}'")
    path = ref if os.path.isabs(ref) else os.path.join(ROOT, ref)
    real = os.path.realpath(path).replace("\\", "/")
    if eid:
        confine = os.path.realpath(os.path.join(ROOT, "engagements", eid, "loot")).replace("\\", "/")
        if not real.startswith(confine + "/"):
            raise ValueError(f"{label} resuelve FUERA de engagements/{eid}/loot/ (traversal/symlink): {ref}")
    else:
        eng_root = os.path.realpath(os.path.join(ROOT, "engagements")).replace("\\", "/")
        if not (real.startswith(eng_root + "/") and re.search(r"/engagements/[^/]+/loot/", real)):
            raise ValueError(f"{label} resuelve FUERA de engagements/<id>/loot/ (traversal/symlink): {ref}")
    if not os.path.isfile(real):
        raise FileNotFoundError(f"no existe {label}: {ref}")
    return real


def _read_credentials(path):
    """Lee usuario/contraseña de un fichero de loot/ (formato `user=...`/`pass=...` o 2 líneas)."""
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    kv = dict(re.findall(r"(?im)^\s*(user(?:name)?|pass(?:word)?)\s*[:=]\s*(.+?)\s*$", data))
    user = kv.get("user") or kv.get("username")
    pw = kv.get("pass") or kv.get("password")
    if not (user and pw):
        lines = [ln for ln in data.splitlines() if ln.strip()]
        if len(lines) >= 2:
            user, pw = user or lines[0].strip(), pw or lines[1].strip()
    if not (user and pw):
        raise ValueError("el fichero de credenciales no trae usuario+contraseña (usa 'user='/'pass=' o 2 líneas)")
    return user, pw


OPERATOR_GUIDE = """\
Playwright no está instalado en este entorno. Adquisición OPERATOR-ASSISTED:
  1) En el ANILLO efímero (deploy/engagement-run.sh <id> --net <red-lab>), instala Playwright:
       pip install playwright && python -m playwright install chromium
     o realiza el login a mano en un navegador con el proxy del engagement.
  2) Autentícate en el login_url EN SCOPE con las credenciales de loot/ (+TOTP: `python tools/totp.py
     --secret-ref <totp_secret_ref>`).
  3) Exporta la sesión (storage-state/cookies) a engagements/<id>/loot/session-<identity>.json.
  4) Fija en el blackboard: identities[<identity>].secret_ref = "engagements/<id>/loot/session-<identity>.json",
     auth.session_type y validated=true. NUNCA pegues el token/cookie en el blackboard."""


def acquire(identity_id, engagement_id=None, headful=False):
    if not os.path.isfile(ENGAGEMENT):
        _err("no hay contracts/engagement.json"); return 2
    scope = load_scope() if load_scope else None
    if scope is None:
        _err("no se pudo cargar scope.json — no se autentica sin scope (fail-closed)"); return 2
    eng, idt = load_identity(identity_id)
    eid = engagement_id or eng.get("engagement_id") or "engagement"
    auth = idt.get("auth") or {}
    login_url = auth.get("login_url")
    if not login_url:
        _err(f"la identidad '{identity_id}' no tiene auth.login_url (define el bloque auth — mejora D)"); return 2
    if not in_scope(login_url, scope):
        _err(f"login_url '{login_url}' NO está en scope — abortado (scope_guard §1). Un IdP de terceros "
             "no está en scope salvo que scope.json lo diga."); return 3

    cred_path = _loot_path(auth["credentials_ref"], "credentials_ref", eid) if auth.get("credentials_ref") else None
    totp_ref = auth.get("totp_secret_ref")
    if totp_ref:
        _loot_path(totp_ref, "totp_secret_ref", eid)  # valida forma+existencia+confinamiento

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        print(OPERATOR_GUIDE)
        _err("Playwright no disponible (adquisición operator-assisted; ver guía arriba)")
        return 4

    os.makedirs(os.path.join(ROOT, "engagements", eid, "loot"), exist_ok=True)
    session_path = os.path.join("engagements", eid, "loot", f"session-{identity_id}.json")
    user = pw = None
    if cred_path:
        user, pw = _read_credentials(cred_path)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(login_url)
        _assert_nav_in_scope(page, scope, login_url)  # el login_url puede 302 a un IdP fuera de scope
        for step in (auth.get("steps") or []):
            _run_step(page, step, user, pw, totp_ref, auth, scope, eid)
            _assert_nav_in_scope(page, scope, "paso de login")  # redirect de servidor tras el paso
        # Persistir la sesión (storage-state Playwright: cookies + localStorage) SOLO en loot/.
        ctx.storage_state(path=os.path.join(ROOT, session_path))
        browser.close()

    # Por stdout: solo la RUTA a referenciar (nunca el material).
    print(json.dumps({
        "identity_id": identity_id,
        "secret_ref": session_path,
        "session_type": auth.get("session_type") or "storage-state",
        "hint": "Fija identities[].secret_ref a esta ruta y validated=true tras comprobar que autentica.",
    }))
    return 0


def _assert_nav_in_scope(page, scope, ctx_label):
    """Aborta (fail-closed) si la URL ACTUAL del navegador cae fuera de scope — el driver es el único
    gate del tráfico del navegador (scope_guard solo ve el comando externo, no las navegaciones)."""
    try:
        cur = page.url
    except Exception:  # noqa: BLE001
        return
    if cur and cur.startswith(("http://", "https://")) and not in_scope(cur, scope):
        raise ValueError(f"navegación FUERA de scope tras {ctx_label}: {_host_of(cur)} "
                         "(¿un redirect a un IdP de terceros?). Abortado — no se improvisa alcance.")


def _run_step(page, step, user, pw, totp_ref, auth, scope, eid):
    action = step.get("action")
    sel = step.get("selector")
    val = step.get("value")
    if step.get("value_ref"):
        with open(_loot_path(step["value_ref"], "steps[].value_ref", eid), encoding="utf-8") as f:
            val = f.read().strip()
    if action == "goto":
        target = val or auth.get("login_url")
        if target and not in_scope(target, scope):   # re-verifica ANTES de navegar
            raise ValueError(f"steps[].goto a un host fuera de scope: {_host_of(target)} — abortado")
        page.goto(target)
    elif action == "fill":
        # Marcadores no sensibles {{user}}/{{pass}} se sustituyen por el material de loot/.
        if val == "{{user}}":
            val = user
        elif val == "{{pass}}":
            val = pw
        page.fill(sel, val or "")
    elif action == "click":
        page.click(sel)
    elif action == "press":
        page.press(sel, val or "Enter")
    elif action == "wait":
        page.wait_for_selector(sel) if sel else page.wait_for_timeout(int(val or 1000))
    elif action == "submit":
        page.click(sel) if sel else page.keyboard.press("Enter")
    elif action == "totp":
        if not totp_ref:
            raise ValueError("paso 'totp' sin auth.totp_secret_ref")
        import totp as _t
        code = _t.totp(_t.read_seed(_loot_path(totp_ref, "totp_secret_ref", eid)))
        page.fill(sel, code)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Adquiere una sesión autenticada (login+TOTP) y la deja en loot/.",
                                 allow_abbrev=False)
    ap.add_argument("--identity", required=True, help="identity_id del bloque identities[] a autenticar.")
    ap.add_argument("--engagement", default=None, help="engagement_id (def.: el del blackboard).")
    ap.add_argument("--headful", action="store_true", help="navegador visible (depuración en el anillo).")
    args = ap.parse_args(argv)
    try:
        return acquire(args.identity, args.engagement, args.headful)
    except (KeyError, ValueError, FileNotFoundError) as e:
        _err(str(e)); return 2


if __name__ == "__main__":
    sys.exit(main())
