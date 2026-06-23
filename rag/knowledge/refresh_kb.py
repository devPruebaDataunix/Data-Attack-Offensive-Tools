#!/usr/bin/env python3
"""
refresh_kb.py — Puebla/actualiza el RAG de CONOCIMIENTO. Análogo a rag/refresh.py.

Clona/actualiza las fuentes a `.cache/` y corre los ingesters.
- Capa 1 (estructurada, kb.db): GTFOBins + LOLBAS + Atomic + ATT&CK. SIEMPRE (ligero, stdlib).
- Capa 2 (semántica, kb_vec.db): HackTricks + PayloadsAllTheThings + PEASS + feeds (0dayfans/HN).
  Solo con --semantic (PESADO: clona repos grandes + embeddings locales; tarda).

Uso:
    python rag/knowledge/refresh_kb.py                 # solo Capa 1
    python rag/knowledge/refresh_kb.py --semantic      # Capa 1 + Capa 2
    python rag/knowledge/refresh_kb.py --semantic-only # solo Capa 2
"""
import os
import runpy
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
SOURCES = {
    "gtfobins": "https://github.com/GTFOBins/GTFOBins.github.io.git",       # privesc/exec Linux
    "lolbas": "https://github.com/LOLBAS-Project/LOLBAS.git",               # LOLBins Windows
    "atomic-red-team": "https://github.com/redcanaryco/atomic-red-team.git",  # comandos por técnica ATT&CK
}
STIX_URL = ("https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
            "master/enterprise-attack/enterprise-attack.json")
# Capa 2 — corpus de prosa (label -> (git_url, slug GitHub para construir URLs de referencia)).
CORPUS = {
    "hacktricks": ("https://github.com/HackTricks-wiki/hacktricks.git", "HackTricks-wiki/hacktricks"),
    "payloads": ("https://github.com/swisskyrepo/PayloadsAllTheThings.git", "swisskyrepo/PayloadsAllTheThings"),
    "peass": ("https://github.com/carlospolop/PEASS-ng.git", "carlospolop/PEASS-ng"),
}


def clone_or_pull(name, url):
    dst = os.path.join(CACHE, name)
    if os.path.isdir(os.path.join(dst, ".git")):
        subprocess.run(["git", "-C", dst, "pull", "--ff-only"], check=False)
    else:
        os.makedirs(CACHE, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", url, dst], check=False)
    return dst


def run(module, argv):
    sys.argv = [module] + argv
    old = sys.path[:]
    sys.path.insert(0, HERE)
    try:
        runpy.run_path(os.path.join(HERE, module), run_name="__main__")
    except SystemExit as e:
        if e.code not in (0, None):
            print(f"[!] {module} salió con {e.code} (continúo).")
    except Exception as e:  # noqa: BLE001 — una fuente caída no aborta el refresco
        print(f"[!] {module} falló: {e} (continúo).")
    finally:
        sys.path = old


def download(url, dst):
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        import urllib.request
        urllib.request.urlretrieve(url, dst)
    except Exception as e:  # noqa: BLE001 — sin red, ATT&CK queda opcional
        print(f"[ATT&CK] no pude descargar el STIX ({e}); omito ATT&CK.")
    return dst


def refresh_layer1():
    print("=== Refresco RAG de conocimiento — Capa 1 (estructurada) ===")
    gtfo = clone_or_pull("gtfobins", SOURCES["gtfobins"])
    run("ingest_gtfobins.py", ["--src", gtfo])

    lolbas = clone_or_pull("lolbas", SOURCES["lolbas"])
    run("ingest_lolbas.py", ["--src", lolbas])

    atomic = clone_or_pull("atomic-red-team", SOURCES["atomic-red-team"])
    run("ingest_atomics.py", ["--src", atomic])

    stix = download(STIX_URL, os.path.join(CACHE, "enterprise-attack.json"))
    if os.path.isfile(stix) and os.path.getsize(stix) > 0:
        run("ingest_attack.py", ["--src", stix])  # sin --platform => Linux+Windows
    else:
        print("[ATT&CK] (omitido) no hay enterprise-attack.json en rag/knowledge/.cache/.")


def refresh_layer2():
    print("=== Refresco RAG de conocimiento — Capa 2 (semántica/embeddings) ===")
    try:
        import sqlite_vec  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError as e:
        print(f"[Capa 2] OMITIDA: falta dependencia ({e}). Instala: pip install sqlite-vec sentence-transformers")
        return
    for label, (url, slug) in CORPUS.items():
        path = clone_or_pull(label, url)
        run("ingest_corpus.py", ["--source", label, "--src", path, "--repo", slug])
    run("ingest_feeds.py", [])  # 0dayfans + Hacker News


def main():
    argv = sys.argv[1:]
    do_l1 = "--semantic-only" not in argv
    do_l2 = ("--semantic" in argv) or ("--semantic-only" in argv)
    if do_l1:
        refresh_layer1()
    if do_l2:
        refresh_layer2()
    print("=== Hecho ===")


if __name__ == "__main__":
    main()
