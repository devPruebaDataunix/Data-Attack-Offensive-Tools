#!/usr/bin/env python3
"""
Tests de la PRESENTACIÓN del bot (bot/botfmt.py): datos (state/intel) -> MarkdownV2. stdlib puro (no
importa `telegram`): se prueba sin red ni token — el corazón de la unificación bot↔state.py.

Corre standalone:  python bot/tests/test_botfmt.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import botfmt as B                    # noqa: E402
from intel.classify import Verdict    # noqa: E402


def test_cve_card_rich_and_escaped():
    r = {"cve": "CVE-2021-44228", "title": "Log4Shell RCE", "vendor": "Apache", "product": "log4j",
         "severity": "critical", "cvss": 10.0, "epss": 0.975, "in_kev": True, "kev_ransomware": True,
         "exploit_public": True, "exploit_maturity": "weaponized",
         "msf_modules": [{"module": "exploit/multi/http/log4shell_header_injection"}, {"module": "x"}],
         "nuclei_templates": ["CVE-2021-44228.yaml"], "cwe": ["CWE-502"],
         "source_refs": ["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"]}
    out = B.cve_card(r)
    assert "CVE\\-2021\\-44228" in out           # título del card: guiones escapados (fuera de code)
    assert "🔴" in out and "CRITICAL" in out      # emoji de severidad + etiqueta
    assert "10\\.0" in out                        # CVSS numérico: el punto se escapa (texto normal)
    assert "log4shell_header_injection" in out    # módulo MSF en `code`
    assert "1 más" in out                         # 2 módulos MSF -> "(+1 más)"
    assert "KEV" in out and "weaponized" in out
    assert "nvd.nist.gov" in out                  # ref como enlace (la URL no se escapa igual)


def test_cve_card_empty():
    assert "Sin datos" in B.cve_card(None)


def test_scope_card_rich():
    scope = {"client": "ACME",
             "authorization": {"type": "pentest", "reference": "PO-42",
                               "valid_from": "2026-01-01", "valid_until": "2026-12-31"},
             "in_scope": {"domains": ["app.acme.com"], "ips": ["10.0.0.5"], "cidrs": ["10.0.1.0/24"]},
             "out_of_scope": {"domains": ["prod.acme.com"]},
             "constraints": {"approval_mode": "critical", "max_actions": 500,
                             "no_dos": True, "no_social_engineering": True,
                             "no_data_exfiltration_real": True}}
    out = B.scope_card(scope)
    assert "ACME" in out
    assert "app.acme.com" in out                  # dominio en `code`: el punto NO se escapa
    assert "🟡" in out and "crítica" in out        # supervisión critical -> chip amarillo + i18n
    assert "500" in out                           # máx acciones
    assert "DoS" in out                           # no-daño listado
    assert "En alcance" in out and "Restricciones" in out


def test_scope_card_empty():
    assert "Sin scope" in B.scope_card(None)
    assert "Sin scope" in B.scope_card({})


def test_findings_card_rich():
    real = Verdict("F-1", "real", "🔴", "SQL injection en login", "10.0.0.1", "high", "explotado", "impacto")
    watch = Verdict("F-2", "watch", "🟠", "Apache 2.4.1 desactualizado", "web01", "medium", "posible", "…")
    grp = {"real": [real], "watch": [watch], "noise": []}
    out = B.findings_card(grp, {"engagement_id": "ENG-1", "phase": "exploitation"})
    assert "ENG\\-1" in out and "explotación" in out         # id (kv -> guion escapado) + fase i18n
    assert "*reales*: 1" in out and "*vigilar*: 1" in out
    assert "F-1" in out and "SQL injection" in out           # finding_id en code (guion sin escapar)
    assert "2\\.4\\.1" in out                                # título en texto normal: puntos escapados
    assert "Reales" in out and "A vigilar" in out


def test_findings_card_empty():
    assert "Sin engagement" in B.findings_card({}, {})


def test_findings_card_unknown_phase_no_double_escape():
    # Regresión: una fase desconocida con '[' NO debe llegar doble-escapada (Rich \\[ + MD2). Con
    # phase_label (crudo) el único escape es el de MD2 -> '\\[' , nunca '\\\\['.
    out = B.findings_card({"real": [], "watch": [], "noise": []},
                          {"engagement_id": "E", "phase": "weird[x]"})
    assert "\\\\[" not in out                                 # sin doble backslash antes del corchete
    assert "weird\\[x\\]" in out                              # exactamente un escape MD2


def _agent_card(name, phase, model="claude-haiku-4-5", peers=None, tools=None):
    return {"name": name, "phase": phase, "model": model, "description": f"desc de {name}",
            "a2a_peers": peers or [], "tools": tools or [], "capabilities": []}


def test_agents_card_groups_by_zone():
    cards = [_agent_card("osint-recon", "recon"),
             _agent_card("web-exploit", "exploitation", model="claude-opus-4-8", peers=["sqlmap"]),
             _agent_card("reporting", "reporting")]
    out = B.agents_card(cards)
    assert "Roster de agentes" in out and "3 agentes" in out
    assert "osint-recon" in out and "web-exploit" in out     # nombres en code (guion sin escapar)
    assert "opus" in out                                     # modelo sin prefijo claude- (esc en normal)
    assert "Reconocimiento" in out and "Explotación" in out  # etiquetas de zona
    assert "1 A2A" in out                                    # web-exploit tiene 1 par A2A


def test_agents_card_empty():
    assert "Sin roster" in B.agents_card([])


def test_agent_card_rich_and_not_found():
    card = _agent_card("adcs", "exploitation", model="claude-sonnet-4-6",
                       peers=["kerberos"], tools=["Bash", "Read"])
    out = B.agent_card(card)
    assert "adcs" in out and "sonnet-4-6" in out             # nombre + modelo en code (literal)
    assert "Explotación" in out                              # zona derivada de la fase
    assert "kerberos" in out and "Bash" in out               # peers A2A + tools en code
    assert "Agente no encontrado" in B.agent_card(None)


def test_help_card_lists_key_commands():
    out = B.help_card()
    for cmd in ("/status", "/agents", "/agent", "/kill", "/cve", "/scope", "/report"):
        assert cmd in out
    assert "control inteligente" in out


def _unescaped(s, ch):
    return sum(1 for i, c in enumerate(s) if c == ch and (i == 0 or s[i - 1] != "\\"))


def test_cards_with_metacharacters_dont_break_md2():
    # Blindaje anti-regresión del escaper (nit del council): una card con TODOS los metacaracteres MD2
    # + campos None/no-str no debe romper el parseo ni dejar un code span abierto.
    nasty = "a*_[]()~`>#+-=|{}.!b"
    card = {"name": nasty, "phase": "exploitation", "model": None, "description": nasty,
            "a2a_peers": [nasty, 123], "tools": [nasty], "capabilities": None}
    detail = B.agent_card(card)
    listing = B.agents_card([card])
    for out in (detail, listing):
        assert isinstance(out, str) and out                  # no crashea ni sale vacío
        assert _unescaped(out, "`") % 2 == 0                 # todo code span abre y cierra
    assert "\\*" in detail                                    # el '*' del contenido fue escapado (esc corrió)


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
