#!/usr/bin/env python3
"""
screenshot.py — Captura de PANTALLA como EVIDENCIA VISUAL (mejora v2.58; idea de BugTraceAI, AGPL →
solo la idea, reimplementación limpia). Playwright captura un screenshot de una URL EN SCOPE y lo deja
en `engagements/<id>/evidence/`, para que `web-exploit` lo LEA (visión nativa del subagente) y CONFIRME
el estado VISUAL de un finding (XSS que renderiza, defacement, dato sensible en pantalla, clickjacking).
Reduce falsos positivos ("el payload devolvió 200 pero, ¿el alert() de verdad se dispara?") y da
evidencia fuerte para el informe.

Seguridad (paridad con acquire_session, mejora D — reusa sus verificadores, sin divergir):
- **Scope fail-closed.** La URL DEBE estar en scope (`scope_guard` vía `acquire_session.in_scope`); se
  re-verifica en cada navegación/redirect (un 302 a un host fuera de scope ABORTA).
- **Artefacto local.** El PNG va SOLO a `engagements/<id>/evidence/` (E3, gitignored); por stdout solo
  la RUTA. El nombre se sanea (basename, sin traversal).
- **Sesión autenticada opcional.** `--identity` carga el storage-state de `loot/session-<id>.json`
  (mejora D) para capturar páginas tras login SIN manejar credenciales aquí.
- **Anillo efímero (mejora C).** El navegador procesa contenido de cliente: su sitio es el contenedor
  efímero por-engagement (`deploy/engagement-run.sh <id> --net <red-lab>`), no el host desnudo.
- **No destructivo.** Navega, espera opcional y captura; no interactúa con la app (salvo un `wait`).

Si Playwright no está instalado, imprime la GUÍA operator-assisted y sale != 0 (sin romper nada).

Uso:
    python tools/screenshot.py --url https://app.acme.example/x --out xss-render [--full-page]
    python tools/screenshot.py --url ... --identity userA --selector "#out" --wait "#out"
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
try:
    from acquire_session import in_scope, _host_of, _assert_nav_in_scope, _loot_path, load_identity
    from scope_guard import load_scope
except Exception:  # noqa: BLE001
    in_scope = None


def _err(msg):
    print(f"screenshot: {msg}", file=sys.stderr)


def _safe_name(name):
    """Basename saneado + extensión .png. Evita traversal/separadores en el nombre del artefacto."""
    base = os.path.basename(str(name or "shot"))
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base) or "shot"
    if not base.lower().endswith(".png"):
        base += ".png"
    return base


def _session_state(identity_id, eid):
    """Ruta al storage-state de una identidad (mejora D) confinada a loot/, o None. Reusa
    `acquire_session.load_identity` + su confinamiento realpath (`_loot_path`) — no diverge ni lee
    credenciales: solo la sesión ya adquirida."""
    if not identity_id:
        return None
    _eng, idt = load_identity(identity_id)
    ref = idt.get("secret_ref")
    if not ref:
        raise ValueError(f"la identidad '{identity_id}' no tiene secret_ref (¿sesión adquirida?)")
    return _loot_path(ref, "identities[].secret_ref", eid)


OPERATOR_GUIDE = """\
Playwright no está instalado en este entorno. Captura OPERATOR-ASSISTED:
  1) En el ANILLO efímero (deploy/engagement-run.sh <id> --net <red-lab>):
       pip install playwright && python -m playwright install chromium
  2) Navega a la URL EN SCOPE y captura la pantalla (full page o el elemento del finding).
  3) Guarda el PNG en engagements/<id>/evidence/ y referencia esa ruta en finding.visual_evidence[].path.
     No saques el artefacto de la zona E3; redáctalo (datos sensibles en pantalla) antes del informe."""


def capture(url, out, engagement_id=None, identity=None, selector=None, full_page=False,
            wait=None, headful=False):
    if in_scope is None:
        _err("no se pudieron cargar los verificadores de scope (scope_guard/acquire_session)"); return 2
    scope = load_scope()
    if scope is None:
        _err("no se pudo cargar scope.json — no se captura sin scope (fail-closed)"); return 2
    if not (url and url.startswith(("http://", "https://"))):
        _err("--url debe ser una URL http(s) EN SCOPE"); return 2
    if not in_scope(url, scope):
        _err(f"URL '{url}' NO está en scope — abortado (scope_guard §1)."); return 3

    eid = engagement_id
    if not eid and os.path.isfile(ENGAGEMENT):
        try:
            eid = json.load(open(ENGAGEMENT, encoding="utf-8")).get("engagement_id")
        except Exception:  # noqa: BLE001
            eid = None
    eid = eid or "engagement"

    try:
        state = _session_state(identity, eid)  # None si no se pide --identity
    except (KeyError, ValueError, FileNotFoundError) as e:
        _err(str(e)); return 2

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        print(OPERATOR_GUIDE)
        _err("Playwright no disponible (captura operator-assisted; ver guía arriba)")
        return 4

    ev_dir = os.path.join(ROOT, "engagements", eid, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    # Ruta CANÓNICA con forward-slash (espeja el pattern del schema y la barrera de blackboard.py:
    # en Windows os.path.join daría '\' y la barrera —que rechaza backslash— tumbaría una captura
    # legítima). El abs_path se reconstruye nativo para escribir el fichero.
    rel_path = "/".join(("engagements", eid, "evidence", _safe_name(out)))
    abs_path = os.path.join(ROOT, *rel_path.split("/"))

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headful)
            ctx = browser.new_context(storage_state=state) if state else browser.new_context()
            page = ctx.new_page()
            page.goto(url)
            _assert_nav_in_scope(page, scope, "goto")  # un redirect fuera de scope aborta
            if wait:
                page.wait_for_selector(wait) if not str(wait).isdigit() else page.wait_for_timeout(int(wait))
            # Re-verifica scope JUSTO antes de capturar: un redirect JS client-side durante el `wait`
            # podría aterrizar fuera de scope y aun así capturaríamos (fail-closed, paridad acquire_session).
            _assert_nav_in_scope(page, scope, "wait")
            if selector:
                page.locator(selector).screenshot(path=abs_path)
            else:
                page.screenshot(path=abs_path, full_page=full_page)
            browser.close()
    except ValueError:
        raise  # scope fail-closed (lo trata main -> return 3/2); no lo enmascares como error de Playwright
    except Exception as e:  # noqa: BLE001 — timeout de goto, --wait/--selector inválido, strict-mode…
        _err(f"fallo de captura (Playwright): {e}")
        return 5

    print(json.dumps({
        "path": rel_path,
        "url": url,
        "host": _host_of(url),
        "element": selector or ("full-page" if full_page else "viewport"),
        "hint": "Léelo (visión) para CONFIRMAR el estado visual y referencia la ruta en "
                "finding.visual_evidence[].path. Redacta datos sensibles antes del informe.",
    }))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Captura un screenshot EN SCOPE como evidencia visual.",
                                 allow_abbrev=False)
    ap.add_argument("--url", required=True, help="URL http(s) EN SCOPE a capturar.")
    ap.add_argument("--out", default="shot", help="nombre del artefacto (se sanea; .png).")
    ap.add_argument("--engagement", default=None, help="engagement_id (def.: el del blackboard).")
    ap.add_argument("--identity", default=None, help="identity_id: captura autenticada con su sesión de loot/.")
    ap.add_argument("--selector", default=None, help="CSS del elemento a capturar (si no, la página).")
    ap.add_argument("--full-page", action="store_true", help="captura la página completa.")
    ap.add_argument("--wait", default=None, help="selector CSS a esperar, o milisegundos.")
    ap.add_argument("--headful", action="store_true", help="navegador visible (depuración en el anillo).")
    args = ap.parse_args(argv)
    try:
        return capture(args.url, args.out, args.engagement, args.identity, args.selector,
                       args.full_page, args.wait, args.headful)
    except (KeyError, ValueError, FileNotFoundError) as e:
        _err(str(e)); return 2


if __name__ == "__main__":
    sys.exit(main())
