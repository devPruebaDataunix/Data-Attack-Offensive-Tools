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


def _scan_or_none(v):
    """scan(operator_only=False) tolerante: True si hay secreto; ante fallo del detector, False (para
    que un fallo de `scan` NO desactive la disciplina de refs, que es pura y no depende de él)."""
    try:
        from redactor import scan
        return bool(scan(v, operator_only=False))
    except Exception:
        return False


def source_hint_reason(text):
    """Motivo de bloqueo si una PISTA de código white-box (`targets[].source_hints[]`, escrita por
    code-recon) filtra un secreto de cliente EN CLARO o rompe la disciplina de referencia — o None.
    El código es zona E3: los campos `label`/`maps_to` son NO sensibles y el material de un
    `kind:secret` va SIEMPRE en `secret_ref` (referencia a loot/), nunca pegado. Distinto del scan
    de auth VIVO: aquí cazamos un DSN/API-key/clave hardcodeada del código volcada a un campo de texto.
    Fail-open ante cualquier error (no rompemos el flujo)."""
    try:
        from redactor import is_loot_ref
        data = json.loads(text)
        hints = []
        for t in (data.get("targets") or []):
            if isinstance(t, dict):
                for h in (t.get("source_hints") or []):
                    if isinstance(h, dict):
                        hints.append(h)
    except Exception:
        return None
    bad = []
    for h in hints:
        # (a) secreto genérico pegado en un campo NO sensible (label/maps_to/source_ref).
        for field in ("label", "maps_to", "source_ref"):
            v = h.get(field)
            if isinstance(v, str) and v and _scan_or_none(v):
                bad.append(f"secreto en source_hints.{field}")
        # (b) kind:secret cuyo secret_ref no es una referencia a loot/ (o falta) = secreto pegado.
        if h.get("kind") == "secret" and not is_loot_ref(h.get("secret_ref")):
            bad.append("source_hints[kind=secret] sin secret_ref -> engagements/<id>/loot/")
    if not bad:
        return None
    return ("Una pista de código white-box (targets[].source_hints[]) filtra material de cliente en "
            "claro o rompe la disciplina de referencia: " + "; ".join(sorted(set(bad))) + ". El código "
            "es zona E3: los `label`/`maps_to` son NO sensibles y todo secreto va REFERENCIADO en "
            "`secret_ref` -> engagements/<id>/loot/, nunca pegado. Mueve el valor a loot/ y deja solo la "
            "referencia file:line.")


def identity_auth_reason(text):
    """Motivo de bloqueo si el bloque `identities[].auth` (mejora D — adquisición de sesión) rompe la
    disciplina de referencia — o None. `credentials_ref`/`totp_secret_ref`/`steps[].value_ref` DEBEN
    apuntar a `engagements/<id>/loot/`; una contraseña/semilla/token pegado en `steps[].value` o en
    esos campos es material de cliente EN CLARO. Fail-open ante cualquier error."""
    try:
        from redactor import is_loot_ref
        data = json.loads(text)
        identities = [i for i in (data.get("identities") or []) if isinstance(i, dict)]
    except Exception:
        return None
    bad = []
    for idt in identities:
        auth = idt.get("auth")
        if not isinstance(auth, dict):
            continue
        who = idt.get("identity_id", "?")
        # (a) los *_ref del bloque auth deben ser referencias a loot/ (no un valor pegado).
        for field in ("credentials_ref", "totp_secret_ref"):
            v = auth.get(field)
            if v is not None and not is_loot_ref(v):
                bad.append(f"identities[{who}].auth.{field} no es una referencia a engagements/<id>/loot/")
        # (b) valores del flujo de login: `value` es NO sensible; un secreto ahí (best-effort, requiere
        #     una palabra clave/formato conocido) = material en claro. El secreto va por `value_ref` a loot/.
        for step in (auth.get("steps") or []):
            if not isinstance(step, dict):
                continue
            vr = step.get("value_ref")
            if vr is not None and not is_loot_ref(vr):
                bad.append(f"identities[{who}].auth.steps[].value_ref no apunta a loot/")
            for field in ("value", "selector"):
                sv = step.get(field)
                if isinstance(sv, str) and sv and sv not in ("{{user}}", "{{pass}}") and _scan_or_none(sv):
                    bad.append(f"identities[{who}].auth.steps[].{field} trae un secreto en claro")
    if not bad:
        return None
    return ("El bloque de adquisición de sesión (identities[].auth, mejora D) filtra material de cliente "
            "en claro o rompe la disciplina de referencia: " + "; ".join(sorted(set(bad))) + ". Usuario/"
            "contraseña van en `credentials_ref`, la semilla TOTP en `totp_secret_ref`, y cada valor "
            "sensible del flujo en `steps[].value_ref` — SIEMPRE a engagements/<id>/loot/, nunca pegado. "
            "Mueve el valor a loot/ y deja solo la referencia.")


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

    reason = blocking_reason(text) or source_hint_reason(text) or identity_auth_reason(text)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
