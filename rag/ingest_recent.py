#!/usr/bin/env python3
"""
ingest_recent.py — Siembra el store con los CVE MÁS RECIENTES desde feeds de frescura.

El resto del RAG está anclado a KEV (explotación confirmada), que va con MESES de retraso respecto a la
publicación. Este ingester añade los CVE recién publicados que aún NO tenemos, desde:
  · CVEDetector  — canal Telegram (preview web público t.me/s/CVEDetector); posts JSON con CVE ID/desc.
  · cvelistV5    — repo oficial MITRE (cves/deltaLog.json), SIN auth; la fuente que OpenCVE agrega por
                   debajo. Cobertura amplia de recientes; enrich_cve5 les rellena nombre/desc/producto.
  · OpenCVE      — API v2 de app.opencve.io (REQUIERE credenciales: OPENCVE_USERNAME/OPENCVE_PASSWORD);
                   si no están, se omite con aviso (no rompe el refresco).
Inserta filas nuevas (in_kev=0) y, en las existentes, solo anota el feed de procedencia (sin pisar KEV).
Los enrichers (cve5/epss/exploits/msf/nuclei) las completan después en el mismo refresco.

ANTI-INYECCIÓN (LLM01): TODO el contenido remoto es DATO inerte. Se parsea como texto; NUNCA se ejecuta
ni se interpreta como instrucción. Refresca periódicamente (idempotente, dedup por cve_id).

Uso:
    python rag/ingest_recent.py                 # CVEDetector (+ OpenCVE si hay credenciales)
    python rag/ingest_recent.py --no-opencve
    OPENCVE_USERNAME=u OPENCVE_PASSWORD=p python rag/ingest_recent.py --opencve-pages 3
"""
import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

import db

CVEDETECTOR_URL = "https://t.me/s/CVEDetector"
OPENCVE_API = "https://app.opencve.io/api/cve"
# Feed de frescura SIN auth: el repo oficial cvelistV5 de MITRE (la fuente que OpenCVE agrega por debajo).
# delta.json = última ventana (pequeña); deltaLog.json = log de muchas ventanas (cobertura amplia reciente).
CVELIST_DELTALOG = "https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/deltaLog.json"
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}")
UA = {"User-Agent": "Mozilla/5.0 (cyberseg-agents recent-cve ingester)"}


def _get(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return html.unescape(re.sub(r"[ \t]+", " ", fragment)).strip()


def cvedetector_entries():
    """Devuelve [{cve_id, name, description, published}] de los posts del canal (DATO inerte)."""
    out, seen = [], set()
    try:
        raw = _get(CVEDETECTOR_URL)
    except Exception as e:  # noqa: BLE001 — feed caído no aborta el refresco
        print(f"[recent:cvedetector] no pude leer el canal: {e}", file=sys.stderr)
        return out
    blocks = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', raw, re.S)
    for b in blocks:
        text = _clean(b)
        m = CVE_RE.search(text)
        if not m:
            continue
        cve = m.group(0).upper()
        if cve in seen:
            continue
        seen.add(cve)
        title = re.search(r'"Title"\s*:\s*"([^"]+)"', text)
        desc = re.search(r"Description\s*:\s*(.+?)(?:\n\s*(?:Reference|Source|Link)\b|$)", text, re.S)
        pub = re.search(r"Published\s*:\s*([^\n|]+)", text)
        out.append({
            "cve_id": cve,
            "name": (title.group(1).strip() if title else cve)[:300],
            "description": (desc.group(1).strip() if desc else text)[:2000],
            "published": (pub.group(1).strip() if pub else None),
        })
    return out


def cvelistv5_entries(limit=400, include_updated=False):
    """CVE recientes desde el deltaLog de MITRE cvelistV5 (sin auth). Recorre snapshots (más reciente
    primero) y junta cveId hasta `limit`. name/description quedan vacíos: los rellena enrich_cve5 desde
    el mismo registro CVE 5.0 que ya descarga (evita doble fetch)."""
    out, seen = [], set()
    try:
        log = json.loads(_get(CVELIST_DELTALOG, timeout=60))
    except Exception as e:  # noqa: BLE001 — feed caído no aborta el refresco
        print(f"[recent:cvelistv5] no pude leer el deltaLog: {e}", file=sys.stderr)
        return out
    for snap in (log if isinstance(log, list) else []):
        bucket = list(snap.get("new", []))
        if include_updated:
            bucket += list(snap.get("updated", []))
        for e in bucket:
            cve = (e.get("cveId") or "").upper()
            if not CVE_RE.fullmatch(cve) or cve in seen:
                continue
            seen.add(cve)
            out.append({"cve_id": cve, "name": None, "description": None,
                        "published": e.get("dateUpdated")})
            if len(out) >= limit:
                return out
    return out


def opencve_entries(pages=2):
    """CVE recientes de OpenCVE (API v2, basic auth por entorno). Sin credenciales -> [] con aviso."""
    user, pwd = os.environ.get("OPENCVE_USERNAME"), os.environ.get("OPENCVE_PASSWORD")
    if not (user and pwd):
        print("[recent:opencve] OMITIDO: define OPENCVE_USERNAME/OPENCVE_PASSWORD para tirar de su API "
              "(la instancia hosted exige cuenta).", file=sys.stderr)
        return []
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    out, seen = [], set()
    for page in range(1, pages + 1):
        try:
            data = json.loads(_get(f"{OPENCVE_API}?page={page}", headers={"Authorization": f"Basic {token}"}))
        except Exception as e:  # noqa: BLE001
            print(f"[recent:opencve] página {page} falló: {e}", file=sys.stderr)
            break
        results = data.get("results", data if isinstance(data, list) else [])
        for it in results:
            cve = (it.get("cve_id") or it.get("id") or "").upper()
            if not CVE_RE.fullmatch(cve) or cve in seen:
                continue
            seen.add(cve)
            out.append({
                "cve_id": cve,
                "name": (it.get("title") or it.get("summary") or cve)[:300],
                "description": (it.get("description") or it.get("summary") or "")[:2000],
                "published": it.get("created_at") or it.get("published"),
            })
    return out


def upsert(conn, entries, feed, now):
    new = 0
    for e in entries:
        cur = conn.execute(
            "INSERT OR IGNORE INTO vulns(cve_id, name, description, in_kev, published_date, "
            "source_feed, updated_at) VALUES(?,?,?,0,?,?,?)",
            (e["cve_id"], e["name"], e["description"], e.get("published"),
             json.dumps([feed]), now),
        )
        if cur.rowcount:
            new += 1
        else:
            # Ya existía (p.ej. de KEV): solo añade el feed a source_feed, sin pisar lo demás.
            row = conn.execute("SELECT source_feed FROM vulns WHERE cve_id=?", (e["cve_id"],)).fetchone()
            feeds = []
            try:
                feeds = json.loads(row["source_feed"]) if row and row["source_feed"] else []
            except (TypeError, ValueError):
                feeds = []
            if feed not in feeds:
                feeds.append(feed)
                conn.execute("UPDATE vulns SET source_feed=? WHERE cve_id=?",
                             (json.dumps(feeds), e["cve_id"]))
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cvedetector", action="store_true")
    ap.add_argument("--no-cvelistv5", action="store_true")
    ap.add_argument("--cvelistv5-limit", type=int, default=400, help="máx CVE recientes de cvelistV5")
    ap.add_argument("--no-opencve", action="store_true")
    ap.add_argument("--opencve-pages", type=int, default=2)
    args = ap.parse_args()

    conn = db.connect()
    now = datetime.now(timezone.utc).isoformat()
    total_seen = total_new = 0

    if not args.no_cvedetector:
        ents = cvedetector_entries()
        n = upsert(conn, ents, "cvedetector", now)
        total_seen += len(ents)
        total_new += n
        print(f"[recent:cvedetector] {len(ents)} CVE en el canal, {n} nuevos al store.")
    if not args.no_cvelistv5:
        ents = cvelistv5_entries(args.cvelistv5_limit)
        n = upsert(conn, ents, "cvelistv5", now)
        total_seen += len(ents)
        total_new += n
        print(f"[recent:cvelistv5] {len(ents)} CVE recientes (deltaLog MITRE), {n} nuevos al store.")
    if not args.no_opencve:
        ents = opencve_entries(args.opencve_pages)
        n = upsert(conn, ents, "opencve", now)
        total_seen += len(ents)
        total_new += n
        if ents:
            print(f"[recent:opencve] {len(ents)} CVE recientes, {n} nuevos al store.")

    db.set_meta(conn, "recent_last_sync", now)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM vulns").fetchone()["c"]
    conn.close()
    print(f"[recent] {total_seen} CVE vistos en feeds, {total_new} nuevos. Store: {total} CVE.")
    if total_new:
        print("[recent] (los nuevos se enriquecen con CVSS/EPSS/exploit en los siguientes pasos del refresco)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[recent] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
