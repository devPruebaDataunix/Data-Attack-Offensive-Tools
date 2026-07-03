#!/usr/bin/env python3
"""
Tests de la capa de formato Telegram (bot/tgfmt.py): escaper MarkdownV2 correcto + helpers de
composición. stdlib puro (no importa `telegram`), 100% testeable sin red.

Corre standalone:  python bot/tests/test_tgfmt.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import tgfmt as F   # noqa: E402


def test_esc_escapes_all_markdownv2_specials():
    # Todos los metacaracteres de MarkdownV2 deben quedar precedidos de '\\'.
    for ch in r"_*[]()~`>#+-=|{}.!":
        assert F.esc(ch) == "\\" + ch, ch
    assert F.esc(None) == "" and F.esc("") == ""
    # texto normal no se toca
    assert F.esc("abc DEF 123") == "abc DEF 123"


def test_esc_real_world_strings():
    assert F.esc("app.cliente.com") == "app\\.cliente\\.com"
    assert F.esc("CVE-2021-44228") == "CVE\\-2021\\-44228"
    assert F.esc("10.0.0.0/24") == "10\\.0\\.0\\.0/24"     # '/' NO es especial en MD2
    assert F.esc("a_b*c") == "a\\_b\\*c"


def test_esc_code_and_url_contexts():
    # dentro de code: solo '`' y '\\'
    assert F.esc_code("a`b\\c") == "a\\`b\\\\c"
    assert F.esc_code("app.cliente.com") == "app.cliente.com"   # el punto NO se escapa en code
    # dentro de (url): ')' y '(' (robustez ante el tokenizador real de Telegram) y '\\'
    assert F.esc_url("http://x/a)b") == "http://x/a\\)b"
    assert F.esc_url("http://x/adv(2024)/d") == "http://x/adv\\(2024\\)/d"   # '(' también se escapa


def test_fragment_helpers():
    assert F.bold("Scope") == "*Scope*"
    assert F.bold("a.b") == "*a\\.b*"                     # el contenido se escapa dentro de la negrita
    assert F.italic("x") == "_x_"
    assert F.code("nmap -sV") == "`nmap -sV`"
    assert F.code("a`b") == "`a\\`b`"
    assert F.link("NVD", "http://x.com/a.b") == "[NVD](http://x.com/a.b)"
    assert F.pre("linea1\nlinea2") == "```\nlinea1\nlinea2\n```"


def test_composition_helpers():
    # kv UNIFICADO: value es un FRAGMENTO (el llamador escapa). Regla única, sin kv_raw.
    assert F.kv("dominios", F.esc("a.com")) == "*dominios*: a\\.com"
    assert F.kv("MSF", F.code("exploit/x")) == "*MSF*: `exploit/x`"
    assert F.bullet(F.code("CVE-1")) == "• `CVE-1`"      # dentro de code, '-' NO se escapa
    assert F.lines("a", "", None, "b") == "a\nb"          # omite vacíos/None
    assert F.lines(["a", "b"], "c") == "a\nb\nc"          # aplana listas
    out = F.card("Scope", [F.kv("dom", F.esc("a.com"))], icon="🎯")
    assert out == "🎯 *Scope*\n*dom*: a\\.com"
    assert F.card("Vacío") == "*Vacío*"                  # título sin cuerpo (í no es metacarácter)
    assert F.card("Con punto.") == "*Con punto\\.*"      # el punto del título sí se escapa


def test_semantic_chips():
    assert F.sev_emoji("critical") == "🔴" and F.sev_emoji("HIGH") == "🟠"
    assert F.sev_emoji(None) == "⚪" and F.sev_emoji("weird") == "⚪"
    assert F.mode_emoji("full") == "🟢" and F.mode_emoji("auto") == "🔴"


def test_plain_fallback_unescapes_without_losing_content():
    # plain() quita SOLO las barras de escape; no pierde caracteres del contenido.
    md2 = F.esc("app.cliente.com/path-1!")
    assert "\\" in md2                                    # el MD2 tenía escapes
    assert F.plain(md2) == "app.cliente.com/path-1!"      # se recupera el texto íntegro
    # una barra que NO precede a un especial se conserva
    assert F.plain("a\\b") == "a\\b"


# ── runner standalone ───────────────────────────────────────────────────────────
def _all_tests():
    return [(n, f) for n, f in sorted(globals().items())
            if n.startswith("test_") and callable(f)]


def main():
    failed = 0
    for name, fn in _all_tests():
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    total = len(_all_tests())
    print(f"\n  {total - failed}/{total} OK" + ("" if not failed else f"  · {failed} FALLOS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
