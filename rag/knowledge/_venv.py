#!/usr/bin/env python3
"""
_venv.py — Entorno virtual DEDICADO para las deps pesadas de la Capa 2 del RAG (sqlite-vec +
sentence-transformers, que arrastra torch). Helper compartido por refresh_kb.py y query_kb.py.

POR QUÉ UN VENV (y no el python del sistema): en Kali/Debian (PEP 668, "externally-managed") instalar
estas deps al python del sistema choca con dpkg. Caso real: torch -> sympy pide `mpmath<1.4`, pero apt
instaló `mpmath 1.4.1` SIN registro de pip, así que pip no puede desinstalarlo ni con
`--break-system-packages` ("uninstall-no-record-file"). Un venv AISLADO parte de cero, instala su propia
`mpmath` y NO toca nada de apt. Además instalamos **torch CPU-only** (índice oficial CPU) para evitar
~2,5 GB de stack CUDA (cuDNN/cuBLAS/NCCL/Triton/...) inútil en una caja sin GPU.

CÓMO LO USAN LOS AGENTES: siguen llamando `python3 rag/knowledge/query_kb.py --semantic`; el script se
re-ejecuta solo con el python del venv cuando ahí están las deps (os.execv). El poblado (refresh_kb) lanza
los ingesters de la Capa 2 con el python del venv. La Capa 1 y `--stats` son stdlib: NO tocan el venv.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(HERE, ".venv")
# Índice CPU de PyTorch: evita el stack CUDA (inútil sin GPU; ahorra ~2,5 GB y tiempo).
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
PIP_TIMEOUT = 3600  # torch tarda; acota el cuelgue sin matar instalaciones lentas


def venv_python():
    """Ruta al intérprete del venv del RAG (exista o no todavía)."""
    if sys.platform == "win32":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def _imports_ok(py):
    """True si ESE intérprete importa AMBAS deps de la Capa 2 (probe por subprocess, silencioso)."""
    try:
        return subprocess.run(
            [py, "-c", "import sqlite_vec, sentence_transformers"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def deps_present():
    """¿Tiene el intérprete ACTUAL las deps de la Capa 2? (sin subprocess)."""
    try:
        import sqlite_vec  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def python_with_semantic_deps(install=True):
    """Devuelve la ruta de un python que SÍ tiene las deps de la Capa 2, o None. Orden: (1) el proceso
    actual; (2) el venv del RAG si ya las tiene; (3) si `install`, crea el venv e instala -> su python;
    (4) None. La usa refresh_kb para elegir con qué python lanzar los ingesters."""
    if deps_present():
        return sys.executable
    vpy = venv_python()
    if os.path.isfile(vpy) and _imports_ok(vpy):
        return vpy
    if install and ensure_venv_and_deps():
        return vpy
    return None


def ensure_venv_and_deps():
    """Crea (si falta) el venv AISLADO del RAG e instala torch CPU-only + sentence-transformers + sqlite-vec.
    Idempotente (si ya importan, no hace nada). Verifica el import al final. Devuelve True/False. ÚNICA fuente
    de verdad de la instalación: la invocan refresh_kb.py (`--semantic` / `--ensure-deps`) y deploy/lib.sh."""
    vpy = venv_python()
    if os.path.isfile(vpy) and _imports_ok(vpy):
        print("[Capa 2] venv del RAG ya listo (sqlite-vec + sentence-transformers).")
        return True
    if not os.path.isfile(vpy):
        print(f"[Capa 2] creando venv AISLADO en rag/knowledge/.venv …", flush=True)
        if subprocess.run([sys.executable, "-m", "venv", VENV_DIR]).returncode != 0:
            print("[Capa 2] no pude crear el venv. Instala 'python3-venv'/'python3-full' y reintenta.")
            return False

    def pip(*args):
        # Sin --quiet: la descarga de torch es grande y conviene ver el progreso. --no-input + stdin
        # cerrado: nunca bloquear esperando entrada (cron/no-interactivo).
        return subprocess.run([vpy, "-m", "pip", "install", "--no-input", *args],
                              stdin=subprocess.DEVNULL, timeout=PIP_TIMEOUT).returncode

    try:
        pip("--upgrade", "pip")
        print("[Capa 2] instalando torch CPU-only (sin CUDA) … (descarga grande, TARDA)", flush=True)
        pip("torch", "--index-url", TORCH_CPU_INDEX)
        print("[Capa 2] instalando sentence-transformers + sqlite-vec …", flush=True)
        # --extra-index-url CPU: si sentence-transformers exige un torch más nuevo, que lo coja del índice
        # CPU y no del PyPI por defecto (que traería el build CUDA y re-bloataría ~2,5 GB).
        pip("sentence-transformers", "sqlite-vec", "--extra-index-url", TORCH_CPU_INDEX)
    except subprocess.TimeoutExpired:
        print("[Capa 2] la instalación superó el límite de tiempo; la abandono (reintenta).")
    except Exception as e:  # noqa: BLE001 — pip ausente/roto: lo reporta el verificador de abajo
        print(f"[Capa 2] no pude ejecutar pip ({e}).")

    if _imports_ok(vpy):
        print("[Capa 2] venv del RAG listo y verificado.")
        return True
    print("[Capa 2] el venv no quedó con las deps importables; revisa el log de pip de arriba.")
    return False


def reexec_in_venv_if_available():
    """Para puntos de entrada que NECESITAN la Capa 2 (p. ej. `query_kb --semantic`): si el proceso actual
    no tiene las deps pero el venv del RAG sí, re-ejecuta este mismo comando con el python del venv
    (os.execv). NO instala nada (eso es de refresh_kb). A prueba de bucles (no re-exec si ya estás en él)."""
    if deps_present():
        return
    vpy = venv_python()
    if (os.path.isfile(vpy)
            and os.path.realpath(vpy) != os.path.realpath(sys.executable)
            and _imports_ok(vpy)):
        os.execv(vpy, [vpy] + sys.argv)
