#!/usr/bin/env python3
"""Tests de la VALIDACIÓN POR VISIÓN (mejora v2.58 — idea de BugTraceAI).

Cubre `tools/screenshot.py` (saneo de nombre, scope fail-closed reusando acquire_session, guía
operator-assisted sin Playwright), el campo `visual_evidence` del esquema, la barrera anti-traversal en
validate_engagement, y el cableado en web-exploit.

    python tests/test_vision.py    (sale 1 si algo falla).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


# ── screenshot.py: saneo de nombre + reuso de scope ─────────────────────────────────
import screenshot as sh  # noqa: E402

check("_safe_name: basename + .png", sh._safe_name("xss-render") == "xss-render.png")
check("_safe_name: quita traversal/separadores",
      sh._safe_name("../../etc/passwd") == "passwd.png" and "/" not in sh._safe_name("a/b/c"))
check("_safe_name: sanea caracteres raros", sh._safe_name("a b$c;d.png") == "a_b_c_d.png")
check("screenshot reusa in_scope de acquire_session (no diverge)", sh.in_scope is not None)
check("screenshot reusa load_identity de acquire_session (no reimplementa el lookup)",
      getattr(sh, "load_identity", None) is not None)

# ── esquema: visual_evidence ────────────────────────────────────────────────────────
sch = json.loads(_read("contracts/finding.schema.json"))
ve = sch["properties"].get("visual_evidence", {})
check("finding.schema tiene 'visual_evidence' (array)", ve.get("type") == "array")
item = ve.get("items", {})
check("visual_evidence.items requiere path", item.get("required") == ["path"])
check("visual_evidence.path con pattern engagements/<id>/evidence|loot/",
      "engagements" in item.get("properties", {}).get("path", {}).get("pattern", ""))
check("vision_verdict enum confirms/refutes/inconclusive",
      set(item.get("properties", {}).get("vision_verdict", {}).get("enum", [])) ==
      {"confirms", "refutes", "inconclusive"})
check("visual_evidence NO en required (retrocompatible)", "visual_evidence" not in sch.get("required", []))

# ── barrera anti-traversal en validate_engagement ───────────────────────────────────
import blackboard as bb  # noqa: E402
base = {"engagement_id": "E", "scope_ref": "s", "phase": "exploitation", "targets": [], "findings": []}


def viol(ve_block):
    f = {"finding_id": "F1", "target_id": "t", "title": "x", "status": "confirmed", "severity": "high",
         "visual_evidence": ve_block}
    return bb.validate_engagement(dict(base, findings=[f]))


check("visual_evidence válido -> OK",
      not any("F1" in v for v in viol([{"path": "engagements/E/evidence/xss.png", "vision_verdict": "confirms"}])))
check("visual_evidence fuera de la zona -> BLOQUEADO",
      any("F1" in v for v in viol([{"path": "/etc/passwd"}])))
check("visual_evidence con '..' (traversal) -> BLOQUEADO",
      any("F1" in v and "traversal" in v for v in viol([{"path": "engagements/E/evidence/../../../etc/passwd"}])))
check("visual_evidence con '..\\' (traversal por backslash, Windows) -> BLOQUEADO",
      any("F1" in v for v in viol([{"path": "engagements/E/evidence/..\\..\\..\\Users\\Alvaro\\.claude\\x"}])))
check("visual_evidence con backslash intermedio -> BLOQUEADO",
      any("F1" in v for v in viol([{"path": "engagements/E/evidence/sub/..\\..\\secret"}])))
check("visual_evidence NO-lista (dict) -> BLOQUEADO (no se ignora en silencio)",
      any("F1" in v for v in viol({"path": "engagements/E/evidence/x.png"})))
check("visual_evidence con elemento no-dict (string) -> BLOQUEADO",
      any("F1" in v for v in viol(["engagements/E/evidence/x.png"])))
# Regresión: la ruta que EMITE screenshot.py es canónica forward-slash y DEBE pasar la barrera en
# Windows (os.path.join daría '\' y la barrera lo rechazaría — por eso screenshot.py canoniza).
_emitted = "/".join(("engagements", "E", "evidence", sh._safe_name("xss render")))
check("ruta emitida por screenshot.py (forward-slash canónica) -> PASA la barrera",
      "\\" not in _emitted and not any("F1" in v for v in viol([{"path": _emitted}])))
check("finding SIN visual_evidence -> intacto (opt-in)",
      not any("F1" in v for v in bb.validate_engagement(dict(base, findings=[
          {"finding_id": "F1", "target_id": "t", "title": "x", "status": "confirmed", "severity": "high"}]))))

# ── operator-guide sin Playwright / scope fail-closed (por subprocess) ───────────────
scr = os.path.join(ROOT, "tools", "screenshot.py")
# URL fuera de scope o sin scope -> sale != 0 y NO crea artefacto (fail-closed). Usamos una URL cualquiera;
# si no hay scope.json, in_scope es fail-closed (False) -> return 3/2.
r = subprocess.run([sys.executable, scr, "--url", "https://not-in-scope.example/x", "--out", "t"],
                   capture_output=True, text=True)
check("screenshot fuera de scope -> exit != 0 (fail-closed)", r.returncode != 0)

# ── cableado en web-exploit ─────────────────────────────────────────────────────────
we = _read(".claude/agents/exploitation/web-exploit.md")
check("web-exploit.md: protocolo de visión (screenshot.py + Read + vision_verdict)",
      "screenshot.py" in we and "visión" in we and "vision_verdict" in we and "visual_evidence" in we)
check("web-exploit.md: E3 (redactar antes del informe)", "E3" in we and "redacta" in we.lower())

print()
if _fail:
    print(f"FALLOS: {len(_fail)} -> {_fail}")
    sys.exit(1)
print("TODOS OK")
