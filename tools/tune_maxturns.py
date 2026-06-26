#!/usr/bin/env python3
"""
tune_maxturns.py — Recomienda `maxTurns` por agente a partir de los turnos REALES usados.

Cruza dos fuentes que ya genera el sistema:
  · la auditoría de SubagentStop (`engagements/*/evidence/subagents.jsonl` + `.claude/audit/subagents.jsonl`),
    que enlaza cada ejecución con su `agent_type` y su `transcript_path`;
  · el transcript de cada subagente (JSONL de Claude Code), del que cuenta los turnos (mensajes assistant).
Agrega por agente (n, p50, p95, máx) y lo compara con el `maxTurns` declarado en `.claude/agents/**/*.md`,
sugiriendo SUBIR (si topa el techo) o bajar (si sobra holgura), con margen.

REAL-DATA: sin engagements ejecutados no hay datos → informa y sale 0. Pensado para correrlo en **Kali**
tras varios engagements (los transcripts viven en `~/.claude/projects/`). Solo stdlib; no toca nada.

    python tools/tune_maxturns.py
    python tools/tune_maxturns.py --json
    python tools/tune_maxturns.py --margin 1.3 --audit <fichero-o-dir-de-subagents.jsonl>
"""
import argparse
import glob
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def declared_maxturns():
    """{nombre_agente: maxTurns} leído del frontmatter de cada .claude/agents/**/*.md."""
    out = {}
    for f in glob.glob(os.path.join(AGENTS_DIR, "**", "*.md"), recursive=True):
        txt = open(f, encoding="utf-8", errors="replace").read()
        m = re.match(r"^---\n(.*?)\n---", txt, re.S)
        if not m:
            continue
        fm = m.group(1)
        name = re.search(r"(?m)^name:\s*(.+?)\s*$", fm)
        mt = re.search(r"(?m)^maxTurns:\s*(\d+)\s*$", fm)
        if name and mt:
            out[name.group(1).strip()] = int(mt.group(1))
    return out


def audit_files(audit_arg):
    """Ficheros subagents.jsonl a leer (de --audit, o de las ubicaciones por defecto)."""
    if audit_arg:
        if os.path.isdir(audit_arg):
            return glob.glob(os.path.join(audit_arg, "**", "subagents.jsonl"), recursive=True)
        return [audit_arg] if os.path.isfile(audit_arg) else []
    found = glob.glob(os.path.join(ROOT, "engagements", "**", "subagents.jsonl"), recursive=True)
    fallback = os.path.join(ROOT, ".claude", "audit", "subagents.jsonl")
    if os.path.isfile(fallback):
        found.append(fallback)
    return found


def audit_records(files):
    """[(agent_type, transcript_path)] de todos los subagents.jsonl, DEDUPLICADO por transcript_path
    (un mismo run puede aparecer en engagements/** y en .claude/audit/ a la vez → no contarlo dos veces)."""
    recs, seen = [], set()
    for fp in files:
        try:
            for line in open(fp, encoding="utf-8", errors="replace"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                at = r.get("agent_type")
                if not at:
                    continue
                tp = r.get("transcript_path")
                if tp:
                    if tp in seen:
                        continue
                    seen.add(tp)
                recs.append((at, tp))
        except OSError:
            continue
    return recs


def count_turns(transcript_path):
    """Turnos del subagente = nº de mensajes 'assistant' en su transcript JSONL. None si no se puede leer."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    turns = 0
    try:
        for line in open(transcript_path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            role = o.get("type") or o.get("role") or (o.get("message") or {}).get("role")
            if role == "assistant":
                turns += 1
    except OSError:
        return None
    return turns


def pct(xs, p):
    if not xs:
        return 0
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return xs[int(k)] if lo == hi else xs[lo] * (hi - k) + xs[hi] * (k - lo)


def recommend(declared, samples, margin):
    """(recomendado, nota) según p95/max usados vs el techo declarado."""
    mx, p95 = max(samples), pct(samples, 95)
    target = max(int(math.ceil(p95 * margin)), mx + 2)  # holgura sobre p95, nunca por debajo del máx visto
    if declared is None:
        return target, "sin maxTurns declarado → fijar"
    if mx >= declared:
        return max(target, declared + 5), f"⚠️ SUBIR — topa el techo ({mx}≥{declared})"
    if p95 * margin < declared * 0.6 and declared - target >= 5:
        return target, f"bajar — sobra holgura (p95={round(p95)} ≪ {declared})"
    return declared, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", help="fichero o dir con subagents.jsonl (def: engagements/ + .claude/audit/)")
    ap.add_argument("--margin", type=float, default=1.3, help="margen sobre p95 (def. 1.3)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    declared = declared_maxturns()
    recs = audit_records(audit_files(args.audit))

    per_agent = {}
    no_transcript = 0
    for agent, tpath in recs:
        t = count_turns(tpath)
        if t is None:
            no_transcript += 1
            continue
        per_agent.setdefault(agent, []).append(t)

    if not per_agent:
        msg = (f"Sin datos de turnos. Registros de auditoría: {len(recs)}; transcripts ilegibles/ausentes: "
               f"{no_transcript}. Ejecuta engagements (en Kali) y reintenta — los transcripts están en "
               f"~/.claude/projects/. (maxTurns declarados leídos: {len(declared)} agentes.)")
        print(json.dumps({"status": "sin-datos", "detail": msg, "declared": declared}, ensure_ascii=False, indent=2)
              if args.json else f"[i] {msg}")
        sys.exit(0)

    report = []
    for agent in sorted(per_agent):
        s = per_agent[agent]
        d = declared.get(agent)
        rec, note = recommend(d, s, args.margin)
        report.append({"agent": agent, "declared": d, "runs": len(s), "p50": round(pct(s, 50)),
                       "p95": round(pct(s, 95)), "max": max(s), "recommended": rec, "note": note})

    if args.json:
        print(json.dumps({"margin": args.margin, "agents": report}, ensure_ascii=False, indent=2))
    else:
        print(f"maxTurns por agente — turnos reales (margen {args.margin}) | transcripts sin leer: {no_transcript}\n")
        print(f"  {'agente':22} {'decl':>4} {'runs':>4} {'p50':>4} {'p95':>4} {'max':>4} {'rec':>4}  nota")
        for r in report:
            print(f"  {r['agent']:22} {str(r['declared'] or '-'):>4} {r['runs']:>4} {r['p50']:>4} "
                  f"{r['p95']:>4} {r['max']:>4} {r['recommended']:>4}  {r['note']}")
        print("\nAplica los 'rec' marcados (⚠️/bajar) en el frontmatter maxTurns y re-corre validate_suite.")
    sys.exit(0)


if __name__ == "__main__":
    main()
