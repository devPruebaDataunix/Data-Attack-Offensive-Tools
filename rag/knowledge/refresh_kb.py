#!/usr/bin/env python3
"""
refresh_kb.py — Puebla/actualiza el RAG de CONOCIMIENTO. Análogo a rag/refresh.py.

Clona/actualiza las fuentes a `.cache/` y corre los ingesters.
- Capa 1 (estructurada, kb.db): GTFOBins + LOLBAS + Atomic + ATT&CK. SIEMPRE (ligero, stdlib).
- Capa 2 (semántica, kb_vec.db): HackTricks + PayloadsAllTheThings + PEASS + 817 skills de ciberseguridad
  (mukul975/Anthropic-Cybersecurity-Skills, Apache-2.0) + canon OWASP de API (API Top 10 2023 / WSTG /
  Cheat Sheet Series, CC BY-SA) + feeds (0dayfans/HN).
  Solo con --semantic (PESADO: clona repos grandes + embeddings locales; tarda).
  OPT-IN (off por defecto): fuentes marcadas `optin` (p.ej. `exploitarium` = PoCs 0-day SIN LICENCIA,
  ROE-only, corpus NO redistribuido) solo se indexan con --with=<label> o KB_OPTIN_SOURCES=<label>.

La Capa 2 vive en un venv AISLADO (rag/knowledge/.venv) con torch CPU-only: ver _venv.py (evita el choque
pip/dpkg de Kali y el stack CUDA). `--semantic` lo crea/usa solo; los agentes consultan vía query_kb.

Uso:
    python rag/knowledge/refresh_kb.py                  # solo Capa 1 (stdlib)
    python rag/knowledge/refresh_kb.py --semantic       # Capa 1 + Capa 2 (crea el venv e instala si falta)
    python rag/knowledge/refresh_kb.py --semantic-only  # solo Capa 2
    python rag/knowledge/refresh_kb.py --semantic --no-install-deps  # Capa 2 sin crear/instalar el venv
    python rag/knowledge/refresh_kb.py --ensure-deps    # solo prepara el venv de la Capa 2 (no puebla)
    python rag/knowledge/refresh_kb.py --semantic --with=exploitarium   # + RAG de 0-day (opt-in, ROE)
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
# Capa 2 — corpus de prosa (label -> spec). `url` y `slug` (para construir las URLs de referencia) son
# obligatorios; `glob` y `branch` son OPCIONALES (por defecto **/*.md sobre 'master') para fuentes que
# publican otro tipo de fichero o usan otra rama.
CORPUS = {
    "hacktricks": {"url": "https://github.com/HackTricks-wiki/hacktricks.git", "slug": "HackTricks-wiki/hacktricks"},
    "payloads": {"url": "https://github.com/swisskyrepo/PayloadsAllTheThings.git", "slug": "swisskyrepo/PayloadsAllTheThings"},
    "peass": {"url": "https://github.com/carlospolop/PEASS-ng.git", "slug": "carlospolop/PEASS-ng"},
    # 817 skills de ciberseguridad MITRE-mapeadas, con avisos de autorización/ROE en su prosa (Apache-2.0).
    # Corpus PASIVO (DATO): no gatea la recuperación; el gate real sigue en scope_guard/approval. Solo los SKILL.md (no
    # references/*.md), rama 'main'. Se referencia la fuente para clonar; el corpus NO se copia al repo.
    "cyber-skills": {"url": "https://github.com/mukul975/Anthropic-Cybersecurity-Skills.git",
                     "slug": "mukul975/Anthropic-Cybersecurity-Skills", "glob": "**/SKILL.md",
                     "branch": "main"},
    # Canon de seguridad ofensiva de API/web (OWASP, CC BY-SA 4.0): el MÉTODO y el razonamiento ACTUAL que
    # consultan api-recon/api-exploit y web-exploit vía `query_kb.py --semantic` (no solo CVEs — el "cómo
    # pensar/probar"). OWASP API Top 10 2023 y **Web Top 10 2025** (definiciones autoritativas; el Web 2025 se
    # publicó en enero 2026 — A01 Broken Access Control sigue #1, A10 "Mishandling of Exceptional Conditions"
    # es NUEVA), WSTG (guía de testing: web/API/GraphQL/JWT/lógica de negocio) y Cheat Sheet Series
    # (REST/GraphQL/JWT/Authorization/Mass-Assignment/SSRF). Se REFERENCIAN para
    # clonar; el corpus NO se versiona en el repo (gitignored). Corpus PASIVO (DATO): no gatea la recuperación
    # ni relaja ninguna puerta. Rama por defecto 'master' (verificado). SIN `pin` a propósito: son repos OWASP
    # oficiales (metodología VIVA, alta vigilancia de maintainers) y el blast radius de una inyección indirecta
    # está acotado por las puertas deterministas (scope_guard/approval/no-daño, por debajo del LLM) + el encuadre
    # "RAG = DATO, no instrucciones" en los agentes. Contrasta con `exploitarium` (single-author, sin licencia),
    # que SÍ lleva pin. Si se quiere anclar integridad/reproducibilidad, pinear y bumpear periódicamente.
    "owasp-api-top10": {"url": "https://github.com/OWASP/API-Security.git",
                        "slug": "OWASP/API-Security", "glob": "editions/2023/en/**/*.md"},
    # glob VERIFICADO (jul-2026) contra el árbol real de OWASP/Top10@master: la edición 2025 vive en
    # `2025/docs/en/` con A01_2025..A10_2025 (NO plano como 2021); `ja/` es traducción → solo inglés.
    # OJO: `_verify_layer2_populated()` cuenta chunks TOTALES, no por-fuente — si un día el glob deja de casar,
    # el corpus web queda vacío en silencio. Reverifica el árbol al poblar en Kali si OWASP reestructura.
    "owasp-web-top10": {"url": "https://github.com/OWASP/Top10.git",
                        "slug": "OWASP/Top10", "glob": "2025/docs/en/**/*.md"},
    "owasp-wstg": {"url": "https://github.com/OWASP/wstg.git",
                   "slug": "OWASP/wstg", "glob": "document/**/*.md"},
    "owasp-cheatsheets": {"url": "https://github.com/OWASP/CheatSheetSeries.git",
                          "slug": "OWASP/CheatSheetSeries", "glob": "cheatsheets/**/*.md"},
    # OPT-IN + ROE — RAG de exploits 0-day. Archivo de PoCs de exploits + writeups de vuln-research de
    # vulnerabilidades POTENCIALMENTE NO REPORTADAS (0-day/n-day). Lo consultan vuln-triage (correlación
    # servicio/versión → ¿hay PoC?) y los agentes de vector (web-exploit/network-exploit/metasploit).
    # ⚠ SIN LICENCIA (all rights reserved): NO se redistribuye — el corpus va gitignored y SOLO se indexa
    # localmente en Kali; aquí solo se REFERENCIA la fuente para clonar. Es DATO PASIVO: NO relaja ninguna
    # puerta (scope_guard/approval siguen) y §3 "sin fuente no se explota" + verificación siguen obligando.
    # Úsalo SOLO bajo ROE que autorice explotación (el autor pide divulgación responsable, no abuso).
    # `pin` fija un commit conocido (el repo sin licencia puede cambiar/desaparecer); quítalo o actualízalo
    # para traer 0-days nuevos. OPT-IN (off por defecto): habilítalo con --with=exploitarium o
    # KB_OPTIN_SOURCES=exploitarium. Solo indexa los writeups .md (no el código PoC crudo).
    "exploitarium": {"url": "https://github.com/bikini/exploitarium.git",
                     "slug": "bikini/exploitarium", "glob": "**/*.md", "branch": "main",
                     "optin": True, "pin": "da60c85abdb354e1160009e7aa8c36941094a865"},
}


def clone_or_pull(name, url, pin=None):
    """Clona/actualiza `url` en .cache/<name>. Si `pin` (un commit), NO hace pull: fija ese commit
    (fetch dirigido + checkout) para un snapshot reproducible (fuentes sin licencia/volátiles)."""
    dst = os.path.join(CACHE, name)
    if os.path.isdir(os.path.join(dst, ".git")):
        if not pin:
            subprocess.run(["git", "-C", dst, "pull", "--ff-only"], check=False)
    else:
        os.makedirs(CACHE, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", url, dst], check=False)
    if pin:
        # el clone shallow puede no contener el commit fijado -> fetch dirigido (GitHub lo permite)
        subprocess.run(["git", "-C", dst, "fetch", "--depth", "1", "origin", pin], check=False)
        subprocess.run(["git", "-C", dst, "checkout", pin], check=False)
    return dst


def _optin_labels(argv):
    """Fuentes OPT-IN habilitadas: de --with=a,b y/o la env KB_OPTIN_SOURCES (coma). Vacío = ninguna
    (las fuentes marcadas `optin` quedan OMITIDAS por defecto — p.ej. exploitarium, sin licencia/0-day)."""
    labels = set()
    for a in argv:
        if a.startswith("--with="):
            labels |= {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
    labels |= {x.strip() for x in os.environ.get("KB_OPTIN_SOURCES", "").split(",") if x.strip()}
    return labels


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


def refresh_layer2(install_deps=True, optin=frozenset()):
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
    for label, spec in CORPUS.items():
        if spec.get("optin") and label not in optin:
            print(f"[Capa 2] fuente opt-in '{label}' OMITIDA (habilítala con --with={label} "
                  f"o KB_OPTIN_SOURCES={label}).")
            continue
        path = clone_or_pull(label, spec["url"], pin=spec.get("pin"))
        argv = ["--source", label, "--src", path, "--repo", spec["slug"]]
        if spec.get("glob"):
            argv += ["--glob", spec["glob"]]
        if spec.get("branch"):
            argv += ["--branch", spec["branch"]]
        _run_ext(py, "ingest_corpus.py", argv)
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
        layer2_ok = refresh_layer2(install_deps, optin=_optin_labels(argv))
    print("=== Hecho ===")
    # Si se pidió la Capa 2 y no quedó poblada, salir con error: el CRON dispara aviso (no rota en silencio)
    # y el deploy entra en su rama de warn en vez de dar un falso "poblada".
    if do_l2 and not layer2_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
