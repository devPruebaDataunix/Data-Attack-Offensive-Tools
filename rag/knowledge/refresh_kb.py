#!/usr/bin/env python3
"""
refresh_kb.py — Puebla/actualiza el RAG de CONOCIMIENTO. Análogo a rag/refresh.py.

Clona/actualiza las fuentes a `.cache/` y corre los ingesters.
- Capa 1 (estructurada, kb.db): GTFOBins + LOLBAS + Atomic + ATT&CK. SIEMPRE (ligero, stdlib).
- Capa 2 (semántica, kb_vec.db): HackTricks + PayloadsAllTheThings + PEASS + feeds (0dayfans/HN).
  Solo con --semantic (PESADO: clona repos grandes + embeddings locales; tarda).

La Capa 2 vive en un venv AISLADO (rag/knowledge/.venv) con torch CPU-only: ver _venv.py (evita el choque
pip/dpkg de Kali y el stack CUDA). `--semantic` lo crea/usa solo; los agentes consultan vía query_kb.

Uso:
    python rag/knowledge/refresh_kb.py                  # solo Capa 1 (stdlib)
    python rag/knowledge/refresh_kb.py --semantic       # Capa 1 + Capa 2 (crea el venv e instala si falta)
    python rag/knowledge/refresh_kb.py --semantic-only  # solo Capa 2
    python rag/knowledge/refresh_kb.py --semantic --no-install-deps  # Capa 2 sin crear/instalar el venv
    python rag/knowledge/refresh_kb.py --ensure-deps    # solo prepara el venv de la Capa 2 (no puebla)
"""
import os
import runpy
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _venv  # noqa: E402 — helper del venv aislado de la Capa 2 (mismo directorio)

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


def _run_ext(py, module, argv):
    """Lanza un ingester de la Capa 2 con el python que TIENE las deps (el venv del RAG, normalmente) como
    subprocess — el proceso actual (python del sistema) no las tiene. cwd=HERE para que `import kb_vec`/
    `embed` resuelvan por el dir del script."""
    try:
        subprocess.run([py, os.path.join(HERE, module), *argv], cwd=HERE, check=False)
    except Exception as e:  # noqa: BLE001 — una fuente caída no aborta el refresco
        print(f"[!] {module} falló: {e} (continúo).")


def refresh_layer2(install_deps=True):
    print("=== Refresco RAG de conocimiento — Capa 2 (semántica/embeddings) ===")
    py = _venv.python_with_semantic_deps(install=install_deps)
    if py is None:
        if install_deps:
            print("[Capa 2] OMITIDA: no pude preparar el venv con las deps. Revisa el log de pip de arriba\n"
                  "         (instala 'python3-venv' si faltaba) y reintenta: python rag/knowledge/refresh_kb.py --semantic")
        else:
            print("[Capa 2] OMITIDA: faltan las deps y --no-install-deps está activo. Prepáralas con:\n"
                  "         python rag/knowledge/refresh_kb.py --semantic   (crea el venv aislado e instala)")
        return False
    for label, (url, slug) in CORPUS.items():
        path = clone_or_pull(label, url)
        _run_ext(py, "ingest_corpus.py", ["--source", label, "--src", path, "--repo", slug])
    _run_ext(py, "ingest_feeds.py", [])  # 0dayfans + Hacker News
    return _verify_layer2_populated()


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
        return False
    print(f"[Capa 2] OK: kb_vec.db poblado ({n} trozos). Detalle: python rag/knowledge/query_kb.py --stats")
    return True


def main():
    argv = sys.argv[1:]
    if "--ensure-deps" in argv:
        # Solo prepara el venv de la Capa 2 (lo invoca deploy/lib.sh). No clona ni puebla nada.
        sys.exit(0 if _venv.ensure_venv_and_deps() else 1)
    do_l1 = "--semantic-only" not in argv
    do_l2 = ("--semantic" in argv) or ("--semantic-only" in argv)
    install_deps = "--no-install-deps" not in argv
    layer2_ok = True
    if do_l1:
        refresh_layer1()
    if do_l2:
        layer2_ok = refresh_layer2(install_deps)
    print("=== Hecho ===")
    # Si se pidió la Capa 2 y no quedó poblada, salir con error: el CRON dispara aviso (no rota en silencio)
    # y el deploy entra en su rama de warn en vez de dar un falso "poblada".
    if do_l2 and not layer2_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
