#!/usr/bin/env python3
"""
refresh.py — Refresco completo del store (KEV + EPSS). Pensado para cron/n8n diario.

Uso:
    python rag/refresh.py
    python rag/refresh.py --epss-all   # re-enriquece EPSS de todo (scores cambian a diario)

Programación recomendada (Windows, Task Scheduler):
    schtasks /Create /SC DAILY /ST 06:00 /TN "cyberseg-rag-refresh" ^
      /TR "python C:\\ruta\\cyberseg-agents\\rag\\refresh.py --epss-all"
"""
import runpy
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def run(module, argv):
    sys.argv = [module] + argv
    old = sys.path[:]
    sys.path.insert(0, HERE)
    try:
        runpy.run_path(os.path.join(HERE, module), run_name="__main__")
    except SystemExit as e:
        if e.code not in (0, None):
            print(f"[!] {module} terminó con código {e.code} (continuo con el resto).")
    except Exception as e:  # noqa: BLE001 - una fuente caída (red/parseo) no aborta todo el refresco
        print(f"[!] {module} falló: {e} (continuo con el resto).")
    finally:
        sys.path = old


def main():
    epss_all = "--epss-all" in sys.argv
    print("=== Refresco RAG de vulnerabilidades (híbrido) ===")
    run("ingest_kev.py", [])                              # 1. KEV (explotación confirmada)
    run("enrich_cve5.py", [])                             # 2. CVSS + SSVC (CVE 5.0, no NVD)
    run("enrich_exploits.py", [])                         # 3. Exploit público (ExploitDB + eip opt)
    run("enrich_msf.py", [])                              # 4. Módulos Metasploit (rapid7)
    run("enrich_nuclei.py", [])                           # 5. Plantillas Nuclei (projectdiscovery)
    run("enrich_epss.py", ["--all"] if epss_all else [])  # 6. EPSS (probabilidad)
    print("=== Hecho ===")


if __name__ == "__main__":
    main()
