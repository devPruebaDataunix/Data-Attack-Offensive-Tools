#!/usr/bin/env python3
"""
run_eval.py — Eval-harness / GATE de capacidad ofensiva (EDD + pass@k; inspirado en el eval-harness de ECC).

Mide OBJETIVAMENTE si el sistema cierra un objetivo de forma autónoma. Un eval (benchmark/evals/*.json)
define target, dificultad y criterio de éxito (p.ej. prueba de root). El grader inspecciona el blackboard
(contracts/engagement.json) y la evidencia del engagement y decide PASS/FAIL; registra pass@k.

GATE del proyecto: el montaje del trailer no se retoma hasta PASS autónomo en un eval Linux 'dificil'.
(El LANZAMIENTO del engagement es manual/externo —`ORCH_APPROVAL_MODE=auto claude`—; este harness GRADÚA
lo ya ejecutado. Auto-lanzar es el siguiente cableado.)

Uso:
    python benchmark/run_eval.py --list
    python benchmark/run_eval.py --eval dockerlabs-injection --engagement contracts/engagement.json --record
    python benchmark/run_eval.py --eval linux-hard-gate --evidence engagements/<id>/evidence --record
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVALS = os.path.join(HERE, "evals")
RESULTS = os.path.join(HERE, "results.jsonl")


def load_evals():
    out = {}
    for f in glob.glob(os.path.join(EVALS, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
            out[d["id"]] = d
        except Exception as e:
            print(f"[!] eval inválido {f}: {e}", file=sys.stderr)
    return out


def gather_text(engagement_path, evidence_dir):
    blobs = []
    if engagement_path and os.path.isfile(engagement_path):
        blobs.append(open(engagement_path, encoding="utf-8", errors="replace").read())
    if evidence_dir and os.path.isdir(evidence_dir):
        for f in glob.glob(os.path.join(evidence_dir, "**", "*"), recursive=True):
            if os.path.isfile(f):
                try:
                    blobs.append(open(f, encoding="utf-8", errors="replace").read())
                except OSError:
                    pass
    return "\n".join(blobs)


def grade(ev, engagement_path, evidence_dir):
    text = gather_text(engagement_path, evidence_dir)
    crit = ev.get("success_criteria", {})
    rx = crit.get("evidence_regex")
    root_proof = bool(rx and re.search(rx, text, re.I | re.M)) if rx else None
    findings = 0
    if engagement_path and os.path.isfile(engagement_path):
        try:
            findings = len(json.load(open(engagement_path, encoding="utf-8")).get("findings", []))
        except Exception:
            pass
    min_findings = findings >= crit.get("min_findings", 0)
    passed = (root_proof is True) and min_findings
    return passed, {"findings": findings, "root_proof": root_proof, "min_findings_ok": min_findings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--eval")
    ap.add_argument("--engagement", default=os.path.join(ROOT, "contracts", "engagement.json"))
    ap.add_argument("--evidence")
    ap.add_argument("--record", action="store_true", help="anota el resultado en results.jsonl (pass@k)")
    args = ap.parse_args()

    evals = load_evals()
    if args.list or not args.eval:
        print("Evals disponibles:")
        for i, d in sorted(evals.items()):
            print(f"  - {i:24} [{d.get('difficulty','?')}/{d.get('platform','?')}] target={d.get('target','?')}")
        if not args.eval:
            return

    ev = evals.get(args.eval)
    if not ev:
        print(f"[!] eval '{args.eval}' no existe (usa --list)", file=sys.stderr)
        sys.exit(2)

    passed, detail = grade(ev, args.engagement, args.evidence)
    verdict = "PASS" if passed else "FAIL"
    print(f"\n[{verdict}] {ev['id']}  ({ev.get('difficulty')}/{ev.get('platform')})  detalle={json.dumps(detail)}")

    if args.record:
        with open(RESULTS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                 "eval": ev["id"], "verdict": verdict, **detail}) + "\n")
        runs = [json.loads(l) for l in open(RESULTS, encoding="utf-8") if l.strip()]
        same = [r for r in runs if r["eval"] == ev["id"]]
        print(f"  pass@{len(same)}: {sum(1 for r in same if r['verdict'] == 'PASS')}/{len(same)}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
