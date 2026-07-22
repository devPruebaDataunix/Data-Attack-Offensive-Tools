#!/usr/bin/env python3
"""
query_triage.py — Consulta del RAG de POLÍTICA DE PROGRAMA para vuln-triage y reporting.

Dada una clase de finding (y opcionalmente su título y la plataforma del programa), devuelve una
recomendación ADVISORY: ¿es una clase típicamente reportable en bug bounty, o una
que los programas suelen rechazar (con su excepción)? ORIENTA la priorización y el filtrado del
informe; NO sustituye el criterio del analista ni el gate determinista de proof-state (mejora F),
y la política OFICIAL del programa PREVALECE.

    python rag/triage/query_triage.py --class self-xss --platform hackerone --json
    python rag/triage/query_triage.py --class idor --json
    python rag/triage/query_triage.py --class csrf --title "CSRF cambia el email" --json
    python rag/triage/query_triage.py --stats
"""
import argparse
import json
import sys

import policy as pol

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser(description="RAG de política de programa (advisory).")
    ap.add_argument("--class", dest="klass", default=None, help="clase/vector del finding (p.ej. self-xss, idor, ssrf)")
    ap.add_argument("--title", default=None, help="título del finding (pista adicional de clase)")
    ap.add_argument("--platform", default=None, help="hackerone | bugcrowd | intigriti | yeswehack")
    ap.add_argument("--stats", action="store_true", help="resumen del dataset (versión, fuentes, cobertura)")
    ap.add_argument("--json", action="store_true", help="salida JSON para el agente")
    args = ap.parse_args()

    data = pol.load_policy()
    if not data:
        msg = "Dataset de política ausente o ilegible (rag/triage/policy_data.json)."
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(2)

    meta = data.get("_meta", {})
    if args.stats:
        out = {
            "version": meta.get("version"),
            "generated": meta.get("generated"),
            "platforms": sorted((data.get("platforms") or {}).keys()),
            "do_not_report_rules": len(data.get("do_not_report") or []),
            "acceptance_classes": len(data.get("acceptance") or []),
            "sources": meta.get("sources"),
            "disclaimer": meta.get("disclaimer"),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False) if args.json
              else f"policy v{out['version']} ({out['generated']}) — {out['do_not_report_rules']} reglas "
                   f"do-not-report, {out['acceptance_classes']} clases de aceptación, "
                   f"plataformas: {', '.join(out['platforms'])}\n  {out['disclaimer']}")
        return

    finding = {"class": args.klass, "title": args.title}
    verdict = pol.classify_finding(finding, platform=args.platform, policy=data)

    if args.json:
        print(json.dumps({"query": finding, "recommendation": verdict}, indent=2, ensure_ascii=False))
    else:
        print(f"Clase: {args.klass or args.title or '?'}  "
              f"(plataforma: {args.platform or 'no especificada'})")
        print(f"  Recomendación (ADVISORY): {verdict['verdict'].upper()}"
              + (f" [{verdict.get('matched')}]" if verdict.get("matched") else ""))
        if verdict.get("reason"):
            print(f"  Motivo: {verdict['reason']}")
        if verdict.get("exception"):
            print(f"  Excepción (SÍ se reporta si): {verdict['exception']}")
        if verdict.get("requires_proof"):
            print(f"  Prueba requerida: {verdict['requires_proof']}")
        print(f"\n  ⚠ {verdict.get('disclaimer', '')}")


if __name__ == "__main__":
    main()
