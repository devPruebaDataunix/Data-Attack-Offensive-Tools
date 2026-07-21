#!/usr/bin/env python3
"""Tests de regresión para los fixes de precisión de scope_guard y header_guard.

Cubre:
- header_guard: strip_heredocs (cuerpo de heredoc = dato) + que la invocación REAL tras el heredoc
  se sigue cazando; y que la cabecera en flag real sigue exigiéndose.
- scope_guard: _is_placeholder + end-to-end (deny placeholder / allow literal in-scope / deny out).

Sin pytest: asserts planos, `python test_guards.py`. El de scope_guard corre el hook como subproceso
con un scope.json temporal para ejercitar main() de punta a punta.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOKS = os.path.join(ROOT, ".claude", "hooks")   # los guards viven en .claude/hooks/, no junto al test
sys.path.insert(0, HOOKS)
import header_guard as H  # noqa: E402
import scope_guard as SG  # noqa: E402

REQ = "BUGCROWD: c4rm3na"
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


# ---------------- header_guard.strip_heredocs / header_gate ----------------
def t_header():
    # 1) invocación real sin cabecera -> bloqueada
    check("real nuclei sin cabecera -> deny",
          H.header_gate("nuclei -u https://t.example.com/x", REQ) is not None)
    # 2) invocación real con cabecera en -H -> permitida
    check("real nuclei con -H -> allow",
          H.header_gate('nuclei -u https://t.example.com/x -H "BUGCROWD: c4rm3na"', REQ) is None)
    # 3) heredoc que ESCRIBE un script mencionando nuclei -> permitido (fix)
    cmd3 = "cat > run.sh <<'EOF'\nnuclei -l hosts.txt -tags citrix,netscaler\nEOF"
    check("heredoc escribe script con nuclei -> allow (fix)", H.header_gate(cmd3, REQ) is None)
    # 4) heredoc que escribe un resumen .md con prosa que cita nuclei -> permitido (fix)
    cmd4 = ("cat > summary.md <<'EOF'\n**Herramienta:** nuclei -tags citrix (no intrusivas)\n"
            "curl https://x.example.com sin cabecera en la prosa\nEOF")
    check("heredoc escribe resumen con prosa -> allow (fix)", H.header_gate(cmd4, REQ) is None)
    # 5) invocación REAL tras cerrar el heredoc, sin cabecera -> se sigue cazando (no es bypass)
    cmd5 = "cat > run.sh <<'EOF'\nfoo bar\nEOF\nnuclei -u https://t.example.com/x"
    check("nuclei real tras heredoc -> deny (no bypass)", H.header_gate(cmd5, REQ) is not None)
    # 6) heredoc con <<- (terminador indentado) -> cuerpo eliminado
    cmd6 = "cat > run.sh <<-EOF\n\tnuclei -u https://t.example.com/x\n\tEOF"
    check("heredoc <<- indentado -> allow (fix)", H.header_gate(cmd6, REQ) is None)
    # 7) proxy explícito exime (comportamiento previo intacto)
    check("proxy -x exime",
          H.header_gate("curl -x http://127.0.0.1:8080 https://t.example.com", REQ) is None)
    # 8) curl con cabecera correcta -> allow
    check("curl con -H -> allow",
          H.header_gate('curl -H "BUGCROWD: c4rm3na" https://t.example.com', REQ) is None)
    # 9) strip_heredocs conserva la línea de apertura y descarta el cuerpo
    stripped = H.strip_heredocs("cat > f <<'EOF'\nSECRETBODY nuclei\nEOF\necho done")
    check("strip conserva apertura", "cat > f" in stripped)
    check("strip descarta cuerpo", "SECRETBODY" not in stripped)
    check("strip conserva comando posterior", "echo done" in stripped)
    # 10) sin here-doc, comando normal intacto
    check("sin heredoc intacto", H.strip_heredocs("echo hola\nls") == "echo hola\nls")
    # 11) required_header vacío -> no-op
    check("sin required_header -> allow",
          H.header_gate("nuclei -u https://t.example.com", "") is None)
    # --- bypass del council: <<palabra espurio no debe tragarse una invocación posterior ---
    # 12) here-string <<<x + curl sin cabecera -> deny (no bypass)
    check("here-string <<< + curl -> deny",
          H.header_gate("cat <<<x\ncurl https://t.example.com", REQ) is not None)
    # 13) << dentro de string + curl sin cabecera -> deny
    check("<< en string + curl -> deny",
          H.header_gate('echo "foo << bar"\ncurl https://t.example.com', REQ) is not None)
    # 14) << en comentario + curl sin cabecera -> deny
    check("<< en comentario + curl -> deny",
          H.header_gate("# ver <<nota\ncurl https://t.example.com", REQ) is not None)
    # 15) left-shift aritmético + curl sin cabecera -> deny
    check("left-shift $((1<<n)) + curl -> deny",
          H.header_gate("echo $((1 << shift))\ncurl https://t.example.com", REQ) is not None)
    # 16) heredoc SIN terminadora (delimitador espurio) + invocación -> deny (fail-closed)
    check("<<EOF sin terminadora + nuclei -> deny",
          H.header_gate("foo <<EOF bar\nnuclei -u https://t.example.com", REQ) is not None)


# ---------------- scope_guard._is_placeholder ----------------
def t_scope_unit():
    for tok in ("$host", "{host}", "${TARGET}", "$1", "`h`", "a.b%c", "x*.example.com"):
        check(f"_is_placeholder({tok!r}) True", SG._is_placeholder(tok) is True)
    for tok in ("ole.connect.optus.com.au", "192.168.1.1", "example.com", "a-b.test.io"):
        check(f"_is_placeholder({tok!r}) False", SG._is_placeholder(tok) is False)


# ---------------- scope_guard end-to-end (subproceso) ----------------
def _run_scope(command, scope):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "contracts"), exist_ok=True)
    with open(os.path.join(d, "contracts", "scope.json"), "w", encoding="utf-8") as f:
        json.dump(scope, f)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    p = subprocess.run([sys.executable, os.path.join(HOOKS, "scope_guard.py")],
                       input=payload, capture_output=True, text=True, cwd=d)
    denied = '"deny"' in p.stdout
    return denied, p.stdout


def t_scope_e2e():
    scope = {"in_scope": {"domains": ["*.optus.com.au"]},
             "out_of_scope": {"domains": ["personal.optus.com.au"]}}
    # placeholder -> deny con motivo accionable
    denied, out = _run_scope("nuclei -u https://$host/logon", scope)
    check("e2e placeholder $host -> deny", denied)
    check("e2e placeholder motivo accionable", "placeholder" in out.lower() or "variable" in out.lower())
    denied, _ = _run_scope("curl https://{target}/x", scope)
    check("e2e placeholder {target} -> deny", denied)
    # host literal in-scope -> allow
    denied, _ = _run_scope("curl https://ole.connect.optus.com.au/logon", scope)
    check("e2e literal in-scope -> allow", not denied)
    # host literal out-of-scope -> deny
    denied, _ = _run_scope("curl https://personal.optus.com.au/x", scope)
    check("e2e literal out-of-scope -> deny", denied)
    # comando sin target (cat) -> allow
    denied, _ = _run_scope("cat contracts/scope.json", scope)
    check("e2e cat sin target -> allow", not denied)


if __name__ == "__main__":
    print("== header_guard =="); t_header()
    print("== scope_guard unit =="); t_scope_unit()
    print("== scope_guard e2e =="); t_scope_e2e()
    print()
    if _fail:
        print(f"FALLOS: {len(_fail)} -> {_fail}")
        sys.exit(1)
    print("TODOS OK")
