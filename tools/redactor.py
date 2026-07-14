#!/usr/bin/env python3
"""
redactor.py — Detector/redactor de secretos DETERMINISTA (control C12, OWASP LLM02).

Solo stdlib (mismo criterio que scope_guard.py / blackboard.py). Nombre `redactor` (no
`secrets`) para no ensombrecer el módulo `secrets` de la stdlib cuando los hooks ponen
`tools/` en sys.path. Dos usos:

- `scan(text, operator_only=False)` -> lista de etiquetas de secreto encontradas. Lo usa el
  hook `.claude/hooks/secret_scan.py` con `operator_only=True` para vigilar el blackboard.
- `redact(text)` -> el texto con cada secreto sustituido por `[REDACTED:<tipo>]`. Lo usa el
  agente `reporting` para SANEAR el informe antes de entregarlo.

Matiz importante de una herramienta ofensiva: descubrir credenciales del CLIENTE es un
hallazgo legítimo, así que NO podemos bloquear ante cualquier "password=...". Por eso cada
patrón lleva `operator_only`: True = casi con seguridad un secreto del OPERADOR/motor (clave
privada, API key de Anthropic, token del bot) que jamás debería aparecer en el engagement de
un cliente — esos son los únicos que el hook bloquea (falsos positivos ~0). Los de proveedor
cloud (AKIA/ghp/AIza/...) podrían ser un hallazgo real, así que solo se REDACTAN, no bloquean.

    python tools/redactor.py <fichero> [<fichero> ...]   # escanea; sale 1 si encuentra algo

Uso en código:
    from redactor import scan, redact
"""
import re
import sys

# (etiqueta, regex, operator_only)
_PATTERNS = [
    ("private_key",    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----", True),
    ("anthropic_key",  r"sk-ant-[A-Za-z0-9_\-]{20,}", True),
    ("telegram_token", r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b", True),
    ("aws_akia",       r"\bAKIA[0-9A-Z]{16}\b", False),
    ("github_pat",     r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", False),
    ("slack_token",    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", False),
    ("google_api",     r"\bAIza[0-9A-Za-z_\-]{35}\b", False),
    ("openai_key",     r"\bsk-[A-Za-z0-9]{32,}\b", False),
    ("jwt",            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", False),
    ("generic_secret",
     r"(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{12,}", False),
    # Material de AUTENTICACIÓN de CLIENTE en claro: el par diferencial de authz (BOLA/BFLA) lleva
    # `Authorization: Bearer …` y `Cookie: session=…` VIVOS. Nunca deben quedar en claro en el
    # blackboard (van referenciados por secret_ref/identity_id). operator_only=False: se REDACTAN en
    # el informe y, en el blackboard, los bloquea secret_scan vía scan_client_auth (ver más abajo).
    ("bearer",         r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-]{16,}=*", False),
    ("cookie",
     r"(?i)(?:(?:set-)?cookie\s*:\s*[^\s;]+=[A-Za-z0-9%._~+/\-]{8,}"
     r"|\b(?:PHPSESSID|JSESSIONID|ASP\.NET_SessionId|connect\.sid|sessionid|session|sid|"
     r"access_token|refresh_token|id_token|auth_token|csrf_?token|xsrf_?token)"
     r"\s*=\s*[A-Za-z0-9%._~+/\-]{16,})", False),
]
_COMPILED = [(label, re.compile(rx), op_only) for label, rx, op_only in _PATTERNS]

# Subconjunto de etiquetas de material de AUTENTICACIÓN de CLIENTE que secret_scan BLOQUEA de forma
# determinista en el blackboard (contracts/engagement.json): SOLO las formas de PRESENTACIÓN de una
# credencial VIVA — `Authorization: Bearer …` (bearer) y `Cookie:`/`Set-Cookie:`/nombres de sesión
# (cookie) —, que el arnés diferencial de authz (BOLA/BFLA) produce y que deben ir referenciadas por
# secret_ref/identity_id, NUNCA en claro. NO se incluyen `jwt` ni `generic_secret` A PROPÓSITO: un
# token/secreto DESCUBIERTO del cliente (p.ej. `api_key=…` hallado en JS) es un HALLAZGO legítimo —
# bloquearlo destruiría el finding (por eso son operator_only=False = solo se REDACTAN). Los patrones
# bearer/cookie casan la credencial viva (token de ≥16 chars presentado como auth), no la mención de un
# hallazgo; y una ruta de secret_ref (engagements/<id>/loot/…) no casa (no lleva "Bearer "/cookie=valor).
CLIENT_AUTH_LABELS = frozenset({"bearer", "cookie"})
# COBERTURA (contrato CONSCIENTE, no exhaustivo — el control primario es la redacción a nivel de prompt;
# este gate es el backstop determinista): caza la PRESENTACIÓN en vivo — `Authorization: Bearer <token>` y
# `Cookie:`/`Set-Cookie:`/nombres de sesión conocidos. NO caza (a propósito o por límite del regex, y así se
# testea en tests/test_secret_scan.py): (1) un token/JWT PELADO sin esas marcas (p.ej. `"session_token":"eyJ…"`
# como valor suelto) → el arnés DEBE serializar el material como cabecera Bearer/Cookie (lo imponen los prompts
# de api-exploit/web-exploit); (2) `Bearer%20…` (espacio URL-encoded); (3) cookie de nombre custom en forma
# pelada. Y SOBRE-bloquea (fail-safe, fricción aceptable) una `Cookie:` no-auth (p.ej. analítica `_ga=`).


def scan(text, operator_only=False):
    """Devuelve las etiquetas (únicas, ordenadas) de secreto presentes en `text`.
    Con `operator_only=True` solo considera los patrones del operador/motor."""
    if not text:
        return []
    found = set()
    for label, rx, op_only in _COMPILED:
        if operator_only and not op_only:
            continue
        if rx.search(text):
            found.add(label)
    return sorted(found)


def scan_client_auth(text):
    """Devuelve las etiquetas de material de AUTENTICACIÓN de CLIENTE VIVO (bearer/cookie) presentes en
    `text`. Lo usa secret_scan sobre el blackboard para BLOQUEAR un `Authorization: Bearer …`/`Cookie:`
    de cliente escrito en claro (debe ir referenciado por secret_ref/identity_id). NO incluye jwt/
    generic_secret (un secreto DESCUBIERTO del cliente es un hallazgo legítimo, solo se redacta) ni los
    secretos del OPERADOR (esos ya los bloquea scan(operator_only=True))."""
    if not text:
        return []
    found = set()
    for label, rx, _op in _COMPILED:
        if label in CLIENT_AUTH_LABELS and rx.search(text):
            found.add(label)
    return sorted(found)


def redact(text):
    """Sustituye cada secreto por `[REDACTED:<tipo>]`. Para sanear el informe."""
    if not text:
        return text
    for label, rx, _op in _COMPILED:
        text = rx.sub(f"[REDACTED:{label}]", text)
    return text


def main(argv):
    if not argv:
        print("uso: python tools/redactor.py <fichero> [<fichero> ...]")
        return 2
    hits = 0
    for path in argv:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            print(f"  [aviso] no se pudo leer {path}: {e}")
            continue
        labels = scan(text)
        if labels:
            hits += 1
            print(f"  [SECRETO] {path}: {', '.join(labels)}")
        else:
            print(f"  [OK] {path}: sin secretos detectados")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
