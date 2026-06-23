#!/usr/bin/env python3
"""
ingest_feeds.py — Ingesta de INTELIGENCIA ACTUAL al RAG semántico (Capa 2): 0dayfans (RSS) + Hacker News.

Da "frescura" al corpus: 0-days/exploits/writeups/CVE recientes. Fuentes confirmadas:
  · 0dayfans (DayZeroSec) — agregador CURADO de seguridad ofensiva, vía su RSS.
  · Hacker News — minado por keywords con la API Algolia (la portada es ruido), siguiendo a primarios.
  · CVEDetector — canal Telegram de CVE recientes (preview web público); su lado ESTRUCTURADO va al RAG
    de CVEs (rag/ingest_recent.py); aquí entra su PROSA para búsqueda semántica.

ANTI-INYECCIÓN: todo el contenido remoto es DATO. Se descarga, se limpia de HTML y se indexa como texto
inerte; NUNCA se ejecuta ni se interpreta como instrucción. Refresca periódicamente (idempotente).

Uso:
    python ingest_feeds.py                 # 0dayfans + Hacker News
    python ingest_feeds.py --no-hn         # solo 0dayfans
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import kb_vec
from embed import Embedder

UA = {"User-Agent": "data-attack-kb/1.0 (offensive-knowledge-rag; research)"}
ODAYFANS_RSS = "https://0dayfans.com/feed.rss"
CVEDETECTOR_URL = "https://t.me/s/CVEDetector"
HN_API = "https://hn.algolia.com/api/v1/search_by_date"
HN_KEYWORDS = ["CVE", "RCE", "privilege escalation", "LPE", "exploit", "0-day",
               "sandbox escape", "kernel exploit", "deserialization", "Show HN security"]
TAG = re.compile(r"<[^>]+>")


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(text):
    return re.sub(r"\s+", " ", TAG.sub(" ", text or "")).strip()


def odayfans_entries():
    out = []
    try:
        root = ET.fromstring(fetch(ODAYFANS_RSS))
    except Exception as e:  # noqa: BLE001 — feed caído no aborta el resto
        print(f"[feeds:0dayfans] no pude leer el RSS: {e}", file=sys.stderr)
        return out
    for item in root.iter("item"):
        title = clean((item.findtext("title") or ""))
        link = (item.findtext("link") or "").strip()
        desc = clean(item.findtext("description") or "")
        if title:
            out.append(("0dayfans", title, desc, link))
    return out


def cvedetector_entries():
    """Posts de CVE recientes del canal CVEDetector (preview web), como prosa para Capa 2 (DATO inerte)."""
    out, seen = [], set()
    try:
        raw = fetch(CVEDETECTOR_URL)
    except Exception as e:  # noqa: BLE001
        print(f"[feeds:cvedetector] no pude leer el canal: {e}", file=sys.stderr)
        return out
    blocks = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', raw, re.S)
    for b in blocks:
        text = clean(re.sub(r"<br\s*/?>", " ", b))
        m = re.search(r"CVE-\d{4}-\d{4,7}", text)
        if not m or m.group(0) in seen:
            continue
        seen.add(m.group(0))
        title = re.search(r'"Title"\s*:\s*"([^"]+)"', text)
        out.append(("cvedetector", (title.group(1).strip() if title else m.group(0)), text,
                    "https://t.me/CVEDetector"))
    return out


def hn_entries(per_kw=30):
    seen, out = set(), []
    for kw in HN_KEYWORDS:
        url = f"{HN_API}?tags=story&hitsPerPage={per_kw}&query=" + urllib.parse.quote(kw)
        try:
            data = json.loads(fetch(url))
        except Exception as e:  # noqa: BLE001
            print(f"[feeds:hn] '{kw}' falló: {e}", file=sys.stderr)
            continue
        for h in data.get("hits", []):
            oid = h.get("objectID")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            title = clean(h.get("title") or "")
            if not title:
                continue
            body = clean(h.get("story_text") or "")
            link = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
            out.append(("hackernews", title, body, link))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-hn", action="store_true", help="omite Hacker News")
    ap.add_argument("--no-cvedetector", action="store_true", help="omite el canal CVEDetector")
    ap.add_argument("--hn-per-kw", type=int, default=30)
    args = ap.parse_args()

    entries = odayfans_entries()
    if not args.no_cvedetector:
        entries += cvedetector_entries()
    if not args.no_hn:
        entries += hn_entries(args.hn_per_kw)
    if not entries:
        print("[feeds] sin entradas (¿red?). No cambio el store.", file=sys.stderr)
        sys.exit(1)

    emb = Embedder()
    conn = kb_vec.connect(emb.dim)
    kb_vec.set_meta(conn, "embed_model", emb.model_name)
    now = datetime.now(timezone.utc).isoformat()

    texts = [f"{title}. {body}".strip() for (_, title, body, _) in entries]
    vectors = emb.encode(texts, is_query=False)
    n_new = 0
    for (src, title, body, link), vec, text in zip(entries, vectors, texts):
        chash = hashlib.sha1(f"{src}|{link}|{title}".encode("utf-8")).hexdigest()
        if kb_vec.add_chunk(conn, source=src, text=text, embedding=vec, chash=chash,
                            platform="", doc=link, title=title, heading="", url=link, updated_at=now):
            n_new += 1
    conn.commit()
    total, by_src = kb_vec.counts(conn)
    conn.close()
    print(f"[feeds] {len(entries)} entradas ({n_new} nuevas). Store kb_vec: {total} | {by_src}")


if __name__ == "__main__":
    main()
