#!/usr/bin/env python3
"""
secret_scan.py — Hook PostToolUse que vigila secretos en claro en el blackboard (control C12,
OWASP LLM02 Sensitive Information Disclosure).

Cuando se escribe contracts/engagement.json, escanea su contenido y BLOQUEA dos clases:
(1) secretos del OPERADOR/motor (clave privada, API key de Anthropic, token del bot) — jamás
deberían acabar en el engagement de un cliente; y (2) material de AUTENTICACIÓN de CLIENTE VIVO
(`Authorization: Bearer …`/`Cookie:`) que produce el arnés diferencial de authz (BOLA/BFLA) — el
token/cookie de una identidad de prueba debe ir REFERENCIADO por secret_ref (engagements/<id>/loot/)
e identificado por identity_id en la evidencia, nunca en claro. Devuelve feedback correctivo al
Orquestador para que lo quite/redacte/referencie. NO bloquea ante credenciales que el equipo DESCUBRE
del CLIENTE (eso es un hallazgo legítimo: solo se redactan) — de ahí la selección quirúrgica de patrones.

Mismo contrato que validate_blackboard.py:
- Recibe JSON por stdin (tool_name / tool_input.file_path).
- Para señalar: imprime {"decision":"block","reason":...} y sale 0.
- Cualquier ambigüedad (no es engagement.json, sin secretos, error) => sale 0 (fail-open).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")


def blocking_reason(text):
    """Motivo de bloqueo (str) si el blackboard trae secretos que NO deben estar en claro, o None si
    está limpio. Dos clases: (1) secretos del OPERADOR/motor (scan operator_only); (2) material de
    AUTENTICACIÓN de CLIENTE VIVO — Bearer/Cookie — del arnés diferencial (scan_client_auth). NO bloquea
    credenciales DESCUBIERTAS del cliente (hallazgo legítimo → solo se redactan). Ante cualquier fallo
    del detector, None (fail-open: jamás rompemos el flujo por un error del guard). Función pura y
    testeable (tests/test_secret_scan.py); main() la usa contra el contenido del blackboard."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from redactor import scan, scan_client_auth
        operator = scan(text, operator_only=True)
        client = scan_client_auth(text)
    except Exception:
        return None  # fail-open: ante CUALQUIER fallo del detector (import O runtime), jamás bloqueamos
    if not operator and not client:
        return None
    parts = []
    if operator:
        parts.append("secretos del OPERADOR/motor (" + ", ".join(operator) + "), que jamás deben acabar "
                     "en el engagement de un cliente")
    if client:
        parts.append("material de AUTENTICACIÓN de CLIENTE en vivo (" + ", ".join(client) + ") en CLARO "
                     "— el token/cookie de una identidad de prueba va REFERENCIADO por secret_ref "
                     "(engagements/<id>/loot/) e identificado por identity_id en la evidencia "
                     "(p.ej. [REDACTED:identity=userA]), nunca en claro")
    return ("Se detectaron en el blackboard (contracts/engagement.json): " + "; ".join(parts) + ". "
            "Quítalos, redáctalos ([REDACTED]) o sustitúyelos por una referencia antes de seguir. (Las "
            "credenciales DESCUBIERTAS del cliente sí van en el hallazgo; esto es para secretos del "
            "propio motor y para el material de auth VIVO de las identidades de prueba.)")


LOOT_REF_RE = None  # compilado perezosamente


def source_hint_reason(text):
    """Motivo de bloqueo si una PISTA de código white-box (`targets[].source_hints[]`, escrita por
    code-recon) filtra un secreto de cliente EN CLARO o rompe la disciplina de referencia — o None.
    El código es zona E3: los campos `label`/`maps_to` son NO sensibles y el material de un
    `kind:secret` va SIEMPRE en `secret_ref` (`^engagements/.+/loot/`), nunca pegado. Distinto del scan
    de auth VIVO: aquí cazamos un DSN/API-key/clave hardcodeada del código volcada a un campo de texto.
    Fail-open ante cualquier error (no rompemos el flujo)."""
    try:
        import re as _re
        from redactor import scan  # detector genérico (operator_only=False)
        data = json.loads(text)
        hints = []
        for t in (data.get("targets") or []):
            if isinstance(t, dict):
                for h in (t.get("source_hints") or []):
                    if isinstance(h, dict):
                        hints.append(h)
    except Exception:
        return None
    loot_ref = _re.compile(r"^engagements/.+/loot/")
    bad = []
    for h in hints:
        # (a) secreto genérico pegado en un campo NO sensible (label/maps_to/source_ref).
        for field in ("label", "maps_to", "source_ref"):
            v = h.get(field)
            if isinstance(v, str) and v:
                try:
                    if scan(v, operator_only=False):
                        bad.append(f"secreto en source_hints.{field}")
                except Exception:
                    pass
        # (b) kind:secret cuyo secret_ref no es una referencia a loot/ (o falta) = secreto pegado.
        if h.get("kind") == "secret":
            sr = h.get("secret_ref")
            if not (isinstance(sr, str) and loot_ref.match(sr)):
                bad.append("source_hints[kind=secret] sin secret_ref -> engagements/<id>/loot/")
    if not bad:
        return None
    return ("Una pista de código white-box (targets[].source_hints[]) filtra material de cliente en "
            "claro o rompe la disciplina de referencia: " + "; ".join(sorted(set(bad))) + ". El código "
            "es zona E3: los `label`/`maps_to` son NO sensibles y todo secreto va REFERENCIADO en "
            "`secret_ref` -> engagements/<id>/loot/, nunca pegado. Mueve el valor a loot/ y deja solo la "
            "referencia file:line.")


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if event.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    fp = (event.get("tool_input") or {}).get("file_path", "") or ""
    if not fp:
        sys.exit(0)
    # Ancla a NUESTRO engagement.json (no a un fichero homónimo de otro repo).
    try:
        same = os.path.realpath(fp) == os.path.realpath(ENGAGEMENT)
    except Exception:
        same = False
    if not same:
        sys.exit(0)

    if not os.path.isfile(ENGAGEMENT):
        sys.exit(0)
    try:
        with open(ENGAGEMENT, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        sys.exit(0)

    reason = blocking_reason(text) or source_hint_reason(text)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
