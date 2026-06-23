#!/usr/bin/env python3
"""
refresh_kb.py — Puebla/actualiza el RAG de CONOCIMIENTO (Capa 1, estructurada). Análogo a rag/refresh.py.

Clona/actualiza las fuentes a `.cache/` y corre los ingesters. La Capa 2 (semántica/embeddings sobre
HackTricks/PEASS/feeds como 0dayfans) se construye aparte.

Uso:
    python rag/knowledge/refresh_kb.py
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


def main():
    print("=== Refresco RAG de conocimiento (Capa 1) ===")
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
    print("=== Hecho ===")


if __name__ == "__main__":
    main()
