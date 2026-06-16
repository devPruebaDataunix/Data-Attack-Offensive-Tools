#!/usr/bin/env python3
"""
run_dryrun.py — Simulación SEGURA del engagement de extremo a extremo (sin atacar nada).

Ejecuta la maquinaria real (gate de scope, RAG triage, blackboard, validación de esquema)
y SIMULA las partes ofensivas (recon y explotación), claramente etiquetadas. Demuestra que
toda la fontanería encaja antes de hacerlo de verdad en una VM con un target autorizado.

Ejecutar desde la raíz del proyecto:
    python dryrun/run_dryrun.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
NOW = datetime.now(timezone.utc).isoformat()

sys.path.insert(0, os.path.join(ROOT, "tools"))
from blackboard import atomic_write_json, validate_engagement  # noqa: E402


def hr(t):
    print("\n" + "=" * 70 + f"\n  {t}\n" + "=" * 70)


def scope_guard(cmd):
    """Llama al hook REAL de scope con un comando Bash simulado."""
    event = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    p = subprocess.run([PY, ".claude/hooks/scope_guard.py"], input=event,
                       capture_output=True, text=True, cwd=ROOT)
    if p.stdout.strip():
        dec = json.loads(p.stdout)["hookSpecificOutput"]
        return "DENY", dec["permissionDecisionReason"]
    return "ALLOW", "(permitido)"


def rag_triage(query, kev_only=True):
    """Llama al RAG REAL (query_vulns) y devuelve los resultados."""
    args = [PY, "rag/query_vulns.py", "--query", query, "--json", "--limit", "3"]
    if kev_only:
        args.append("--kev-only")
    p = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    return json.loads(p.stdout)["results"] if p.returncode == 0 else []


def main():
    scope = json.load(open(os.path.join(ROOT, "contracts", "scope.json"), encoding="utf-8"))
    eng = {"engagement_id": scope["engagement_id"], "scope_ref": "contracts/scope.json",
           "phase": "init", "updated_at": NOW, "targets": [], "findings": [],
           "lessons": [], "evidence": []}
    print(f"Engagement: {eng['engagement_id']}  ({scope['client']})")

    # ---- FASE 1: RECON (SIMULADO) ----
    hr("FASE 1 · RECON  [SIMULADO — en real lo harían osint-recon + active-recon]")
    eng["phase"] = "recon"
    eng["targets"] = [
        {"target_id": "T-001", "asset": "192.168.56.10", "asset_type": "ip", "in_scope": True,
         "discovered_by": "active-recon",
         "open_ports": [
             {"port": 80, "protocol": "tcp", "service": "Apache httpd", "version": "2.4.49"},
             {"port": 8090, "protocol": "tcp", "service": "Atlassian Confluence", "version": "7.13.0"}],
         "technologies": ["Apache HTTP Server 2.4.49", "Atlassian Confluence 7.13.0"]},
        {"target_id": "T-002", "asset": "http://app.lab.local", "asset_type": "url", "in_scope": True,
         "discovered_by": "osint-recon", "technologies": ["PHP", "MySQL"]},
    ]
    for t in eng["targets"]:
        print(f"  [recon] {t['target_id']} {t['asset']:22} {', '.join(t.get('technologies', []))}")

    # ---- FASE 2: GATE DE SCOPE (REAL) ----
    hr("FASE 2 · GATE DE SCOPE  [REAL — hook scope_guard.py]")
    for cmd in ["nmap -sV 192.168.56.10",            # in scope
                "curl http://app.lab.local/",         # in scope
                "nmap -sV acme.example",              # OUT of scope
                "curl https://8.8.8.8"]:              # OUT of scope
        verdict, reason = scope_guard(cmd)
        mark = "OK " if verdict == "ALLOW" else "BLOQUEADO"
        print(f"  [{mark:9}] {cmd}")
        if verdict == "DENY":
            print(f"             -> {reason}")

    # ---- FASE 3: TRIAGE (REAL — RAG KEV/exploit/EPSS/CVSS) ----
    hr("FASE 3 · TRIAGE  [REAL — vuln-triage consulta el RAG]")
    eng["phase"] = "triage"
    fid = 0
    for query in ["Apache HTTP Server", "Atlassian Confluence"]:
        res = rag_triage(query)
        if not res:
            continue
        r = res[0]  # el de mayor prioridad
        fid += 1
        finding = {
            "finding_id": f"F-{fid:03d}", "target_id": "T-001",
            "title": r["title"], "status": "candidate", "severity": r["severity"],
            "cvss": r["cvss"], "cvss_vector": r.get("cvss_vector"),
            "cve": [r["cve"]], "epss": r["epss"],
            "exploit_public": r["exploit_public"], "exploit_sources": r["exploit_sources"],
            "ssvc": r.get("ssvc"), "attack_technique": "T1190",
            "discovered_by": "vuln-triage", "source_refs": r["source_refs"],
        }
        eng["findings"].append(finding)
        flags = ("KEV " if r["in_kev"] else "") + ("EXPLOIT" if r["exploit_public"] else "")
        print(f"  [triage] {finding['finding_id']} {r['cve']:18} CVSS={r['cvss']} "
              f"EPSS={r['epss']:.3f} {flags}  {r['title'][:42]}")

    # ---- FASE 4: EXPLOTACIÓN (SIMULADA) ----
    hr("FASE 4 · EXPLOTACIÓN  [SIMULADO — en real: web/network-exploit, con visto bueno humano]")
    eng["phase"] = "exploitation"
    sim_evidence = {
        "CVE-2021-41773": "GET /cgi-bin/.%2e/%2e%2e/etc/passwd -> 200 (root:x:0:0 ...) [SIMULADO]",
        "CVE-2022-26134": "GET /%24%7B...OGNL...%7D/ -> ejecución de comando confirmada [SIMULADO]",
    }
    for f in eng["findings"]:
        cve = f["cve"][0]
        f["status"] = "exploited"
        f["confirmed_by"] = "network-exploit"
        f["evidence"] = sim_evidence.get(cve, "[SIMULADO]")
        f["reproduction"] = f"Reproducción del exploit de {cve} (ver evidencia). [SIMULADO]"
        f["impact"] = "Ejecución de código / lectura de ficheros en el host de laboratorio."
        f["remediation"] = "Actualizar el producto a una versión parcheada."
        print(f"  [exploit] {f['finding_id']} {cve} -> status=exploited (evidencia simulada)")
    # Hallazgo app-level sin CVE (descubierto manualmente por web-exploit)
    eng["findings"].append({
        "finding_id": f"F-{len(eng['findings'])+1:03d}", "target_id": "T-002",
        "title": "Inyección SQL no autenticada en /login (parámetro user)",
        "status": "exploited", "severity": "critical", "cvss": 9.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe": "CWE-89", "owasp": "A03:2021-Injection", "attack_technique": "T1190",
        "exploit_public": False, "discovered_by": "web-exploit", "confirmed_by": "web-exploit",
        "evidence": "user=' OR '1'='1'-- - -> bypass de autenticación [SIMULADO]",
        "reproduction": "Enviar user=' OR '1'='1'-- - en /login. [SIMULADO]",
        "impact": "Acceso administrativo sin credenciales y lectura de la base de datos.",
        "remediation": "Consultas parametrizadas y validación de entrada.",
        "source_refs": ["https://owasp.org/Top10/A03_2021-Injection/"],
    })
    print(f"  [exploit] F-{len(eng['findings']):03d} SQLi /login -> status=exploited (manual, simulado)")

    # ---- ESCRIBIR BLACKBOARD + VALIDAR ----
    hr("BLACKBOARD · escribir y validar contra los esquemas")
    eng["phase"] = "reporting"
    eng["updated_at"] = NOW
    out = os.path.join(ROOT, "contracts", "engagement.json")
    atomic_write_json(out, eng)  # escritura atómica (tmp + os.replace)
    # Validación de esquema: targets + findings + lessons + evidence (tools/blackboard.py)
    violations = validate_engagement(eng)
    for v in violations:
        print(f"  [!] {v}")
    print(f"  engagement.json escrito: {len(eng['targets'])} targets, {len(eng['findings'])} findings")
    print(f"  validación de esquema: {'OK — blackboard cumple los esquemas' if not violations else 'FALLOS arriba'}")

    # ---- ANÁLISIS DE COHERENCIA (REAL — /analyze adaptado de spec-driven) ----
    hr("COHERENCIA · tools/analyze_engagement.py  [REAL — puerta de calidad pre-informe]")
    rc = subprocess.run([PY, os.path.join(ROOT, "tools", "analyze_engagement.py")]).returncode
    print(f"\n  analyze_engagement -> {'OK (engagement coherente)' if rc == 0 else 'INCOHERENCIAS (revisar arriba)'}")

    print(f"\n  fase final: {eng['phase']}  ->  listo para el agente reporting")


if __name__ == "__main__":
    main()
