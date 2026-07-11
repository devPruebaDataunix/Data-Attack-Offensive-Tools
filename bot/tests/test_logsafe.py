#!/usr/bin/env python3
"""Tests de logsafe (redacción del token del bot en los logs). stdlib puro, sin red.

Corre standalone:  python bot/tests/test_logsafe.py
"""
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import logsafe as LS  # noqa: E402


def test_redacts_token_in_getupdates_url():
    tok = "8123456789:AAHkzabcdefghijklmnopqrstuvwxyz012345"
    line = f'HTTP Request: POST https://api.telegram.org/bot{tok}/getUpdates "HTTP/1.1 200 OK"'
    out = LS.redact_secrets(line, tok)
    assert tok not in out and "[REDACTED]" in out
    assert "getUpdates" in out                      # solo tapa el secreto, no destroza el resto


def test_redacts_by_pattern_without_known_token():
    # aunque NO pasemos el token literal, el patrón lo caza igualmente
    tok = "1234567890:BBFxyzabcdefghijklmnopqrstuvwxyz01"
    out = LS.redact_secrets(f".../bot{tok}/getUpdates", "")
    assert tok not in out and "[REDACTED]" in out


def test_non_secret_text_untouched():
    s = "Menú de comandos registrado en 1/1 chat(s) de la allowlist."
    assert LS.redact_secrets(s, "8123456789:AAHkzabcdefghijklmnopqrstuvwxyz012345") == s


def test_none_and_empty_safe():
    assert LS.redact_secrets(None, "") == ""
    assert LS.redact_secrets("", "tok") == ""


def test_filter_rewrites_record():
    tok = "8123456789:AAHkzabcdefghijklmnopqrstuvwxyz012345"
    flt = LS.RedactFilter(tok)
    rec = logging.LogRecord("httpx", logging.INFO, __file__, 1,
                            "GET https://api.telegram.org/bot%s/getUpdates", (tok,), None)
    assert flt.filter(rec) is True                  # el filtro nunca descarta (solo reescribe)
    assert tok not in rec.getMessage() and "[REDACTED]" in rec.getMessage()


def test_exc_info_traceback_redacted():
    # MUST del council: un log.exception con una excepción de httpx cuyo str() lleva la URL con el token
    # filtraría el token en el TRACEBACK (que el Formatter renderiza aparte, sin filtros). El filtro debe
    # redactar exc_text.
    tok = "8123456789:AAHkzabcdefghijklmnopqrstuvwxyz012345"
    flt = LS.RedactFilter(tok)
    try:
        raise RuntimeError(f"boom al llamar https://api.telegram.org/bot{tok}/getUpdates")
    except RuntimeError:
        rec = logging.LogRecord("databot", logging.ERROR, __file__, 1, "runner", (), sys.exc_info())
    flt.filter(rec)
    out = logging.Formatter("%(message)s").format(rec)     # el Formatter añade el traceback desde exc_text
    assert "Traceback" in out                              # el traceback SÍ se renderiza
    assert tok not in out and "[REDACTED]" in out          # …pero con el token enmascarado


def test_install_quiets_http_and_adds_filter():
    root = logging.getLogger()
    h = logging.StreamHandler()
    root.addHandler(h)
    try:
        LS.install("8123456789:AAHkzabcdefghijklmnopqrstuvwxyz012345")
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert any(isinstance(f, LS.RedactFilter) for f in h.filters)
    finally:
        root.removeHandler(h)


def _all():
    return [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]


def main():
    failed = 0
    for name, fn in _all():
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    total = len(_all())
    print(f"\n  {total - failed}/{total} OK" + ("" if not failed else f"  · {failed} FALLOS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
