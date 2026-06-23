#!/usr/bin/env python3
"""
ingest_attack.py — Ingesta MITRE ATT&CK (Enterprise, STIX 2.1) al RAG de conocimiento.

Aporta el marco TÁCTICO: tácticas, técnicas y sub-técnicas con descripción y plataformas, para que
los agentes razonen por TTP (no solo por CVE/binario). Fuente: enterprise-attack.json de
mitre-attack/attack-stix-data. Los COMANDOS concretos por técnica los aporta Atomic Red Team (ingester aparte).

Por defecto ingiere TODA técnica con plataforma Linux y/o Windows, fijando platform=linux/windows/multi
(las cross-platform quedan 'multi', que la query trata como cualquier plataforma). Con --platform filtra
a una sola (retrocompatible).

Uso:
    python ingest_attack.py --src <ruta a enterprise-attack.json> [--platform Linux]
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import kb

ATTACK_REF = "https://attack.mitre.org/techniques/"

# La táctica MITRE (kill_chain_phase) usa nombres largos y, en la versión actual de ATT&CK, parte la
# antigua "defense-evasion" en `stealth` + `defense-impairment`. Normalizo `category` al vocabulario que
# usan el resto de fuentes accionables (GTFOBins/LOLBAS/Atomic) para que `--category` filtre uniforme.
# La columna `tactic` conserva la(s) táctica(s) MITRE exacta(s) (fidelidad).
CATEGORY_NORM = {
    "privilege-escalation": "privesc",
    "lateral-movement": "lateral",
    "exfiltration": "exfil",
    "stealth": "defense-evasion",
    "defense-impairment": "defense-evasion",
}


def tech_external(obj):
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id"), ref.get("url")
    return None, None


def platform_field(platforms, filt):
    """Plataforma a guardar. Con --platform: esa, en minúscula. Sin filtro: linux/windows/multi
    según x_mitre_platforms (None si no toca ni Linux ni Windows -> fuera de alcance)."""
    if filt:
        return filt.lower()
    lin, win = "Linux" in platforms, "Windows" in platforms
    if lin and win:
        return "multi"
    return "linux" if lin else ("windows" if win else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="enterprise-attack.json (STIX 2.1)")
    ap.add_argument("--platform", default=None,
                    help="filtra a una sola plataforma (Linux/Windows/macOS); por defecto Linux+Windows")
    args = ap.parse_args()
    try:
        data = json.load(open(args.src, encoding="utf-8"))
    except Exception as e:
        print(f"[ATT&CK] No pude leer {args.src}: {e}", file=sys.stderr)
        sys.exit(2)

    conn = kb.connect()
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for obj in data.get("objects", []):
        if obj.get("type") != "attack-pattern" or obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        platforms = obj.get("x_mitre_platforms") or []
        if args.platform and args.platform not in platforms:
            continue
        plat = platform_field(platforms, args.platform)
        if plat is None:
            continue
        tid, url = tech_external(obj)
        if not tid:
            continue
        phases = [p.get("phase_name") for p in obj.get("kill_chain_phases", [])]
        tactic = ",".join(p for p in phases if p)
        category = CATEGORY_NORM.get(phases[0], phases[0]) if phases else "ttp"
        name = obj.get("name", "")
        desc = (obj.get("description") or "").strip().replace("\n", " ")
        tags = json.dumps(sorted({tid.lower(), name.lower(), *(p for p in phases if p)}))
        conn.execute(
            "INSERT OR IGNORE INTO techniques(source,platform,category,tactic,mitre_id,name,subtype,"
            "preconditions,command,description,tags,source_ref,updated_at) "
            "VALUES('attack',?,?,?,?,?,'technique','','',?,?,?,?)",
            (plat, category, tactic, tid, name,
             desc[:800], tags, url or (ATTACK_REF + tid.replace(".", "/")), now),
        )
        n += 1
    kb.set_meta(conn, "attack_last_sync", now)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM techniques").fetchone()["c"]
    conn.close()
    scope = args.platform or "Linux+Windows"
    print(f"[ATT&CK] {n} técnicas ({scope}) insertadas. Store: {total} técnicas.")


if __name__ == "__main__":
    main()
