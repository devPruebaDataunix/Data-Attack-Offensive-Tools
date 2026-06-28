#!/usr/bin/env python3
"""
refresh_kb.py — Puebla/actualiza el RAG de CONOCIMIENTO. Análogo a rag/refresh.py.

Clona/actualiza las fuentes a `.cache/` y corre los ingesters.
- Capa 1 (estructurada, kb.db): GTFOBins + LOLBAS + Atomic + ATT&CK. SIEMPRE (ligero, stdlib).
- Capa 2 (semántica, kb_vec.db): HackTricks + PayloadsAllTheThings + PEASS + feeds (0dayfans/HN).
  Solo con --semantic (PESADO: clona repos grandes + embeddings locales; tarda).

Uso:
    python rag/knowledge/refresh_kb.py                  # solo Capa 1
    python rag/knowledge/refresh_kb.py --semantic       # Capa 1 + Capa 2 (auto-instala sus deps si faltan)
    python rag/knowledge/refresh_kb.py --semantic-only  # solo Capa 2
    python rag/knowledge/refresh_kb.py --semantic --no-install-deps  # Capa 2 SIN auto-instalar sus deps
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


def _semantic_deps_present():
    try:
        import sqlite_vec  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _install_semantic_deps():
    """Instala las deps de la Capa 2 (sqlite-vec + sentence-transformers, que arrastra torch) en ESTE
    intérprete. Portable: prueba con --break-system-packages (Kali/Debian son PEP 668 'externally-managed')
    y, si ese pip no lo acepta, sin él. NO usa --quiet: la descarga de torch es grande y conviene ver el
    progreso. `--no-input` + stdin cerrado + timeout para no bloquear nunca en no-interactivo. Devuelve True
    solo si después los módulos importan: cubre el caso aún-no-importado (un módulo ya cargado en el proceso
    NO se reemplaza). ESPEJO de ensure_semantic_deps() en deploy/lib.sh — si tocas una, toca la otra."""
    print("[Capa 2] Faltan dependencias (sqlite-vec / sentence-transformers). Las instalo ahora: descargan\n"
          "         torch (~cientos de MB) y TARDA. Desactívalo con --no-install-deps.", flush=True)
    pkgs = ["sqlite-vec", "sentence-transformers"]
    for extra in (["--break-system-packages"], []):
        try:
            if subprocess.run([sys.executable, "-m", "pip", "install", "--no-input", *extra, *pkgs],
                              stdin=subprocess.DEVNULL, timeout=1800).returncode == 0:
                break
        except subprocess.TimeoutExpired:
            print("[Capa 2] la instalación de deps superó el límite de tiempo (30 min); la abandono.")
        except Exception as e:  # noqa: BLE001 — pip ausente/roto: lo reporta el verificador de abajo
            print(f"[Capa 2] no pude ejecutar pip ({e}).")
    import importlib
    importlib.invalidate_caches()
    return _semantic_deps_present()


def refresh_layer2(install_deps=True):
    print("=== Refresco RAG de conocimiento — Capa 2 (semántica/embeddings) ===")
    if not _semantic_deps_present():
        manual = ("python3 -m pip install --break-system-packages sqlite-vec sentence-transformers"
                  "  (o: sudo ./deploy/auto-deploy.sh --semantic-rag)")
        if not install_deps:
            print(f"[Capa 2] OMITIDA: faltan deps y --no-install-deps está activo. Instálalas con:\n         {manual}")
            return
        if not _install_semantic_deps():
            print(f"[Capa 2] OMITIDA: no pude instalar/verificar las deps. Instálalas a mano:\n         {manual}")
            return
    for label, (url, slug) in CORPUS.items():
        path = clone_or_pull(label, url)
        run("ingest_corpus.py", ["--source", label, "--src", path, "--repo", slug])
    run("ingest_feeds.py", [])  # 0dayfans + Hacker News
    _verify_layer2_populated()


def _verify_layer2_populated():
    """Importar las deps NO basta: el primer embedding descarga el modelo (BAAI/bge-small-en-v1.5) de
    HuggingFace; sin red a HF (o con un clone interrumpido) la ingesta falla, `run()` se la traga y kb_vec.db
    queda VACÍO. Comprueba el resultado REAL (conteo de `chunks`, SQLite normal — no carga sqlite-vec) y avisa
    con la causa probable, para no terminar con un falso 'OK' como el que motivó este fix."""
    import sqlite3
    vdb = os.path.join(HERE, "kb_vec.db")
    n = 0
    if os.path.isfile(vdb):
        try:
            c = sqlite3.connect(vdb)
            n = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            c.close()
        except sqlite3.Error:
            n = 0
    if n == 0:
        print("[Capa 2] AVISO: kb_vec.db quedó VACÍO aun con las deps presentes. Causa probable: no se pudo\n"
              "         descargar el modelo de embeddings (BAAI/bge-small-en-v1.5) de HuggingFace, o se\n"
              "         interrumpió un clone. Revisa la conectividad a huggingface.co y reintenta;\n"
              "         comprueba con: python rag/knowledge/query_kb.py --stats")
    else:
        print(f"[Capa 2] OK: kb_vec.db poblado ({n} trozos). Detalle: python rag/knowledge/query_kb.py --stats")


def main():
    argv = sys.argv[1:]
    do_l1 = "--semantic-only" not in argv
    do_l2 = ("--semantic" in argv) or ("--semantic-only" in argv)
    install_deps = "--no-install-deps" not in argv
    if do_l1:
        refresh_layer1()
    if do_l2:
        refresh_layer2(install_deps)
    print("=== Hecho ===")


if __name__ == "__main__":
    main()
