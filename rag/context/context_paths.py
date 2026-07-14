#!/usr/bin/env python3
"""
context_paths.py — Resolución y AISLAMIENTO de rutas del RAG de CONTEXTO per-engagement.

El RAG de contexto es el TERCER store, arquitectónicamente distinto de los otros dos:
- `rag/vulns.db`      — QUÉ es vulnerable (CVE/KEV/EPSS). General, cross-engagement.
- `rag/knowledge/`    — CÓMO explotar/razonar (técnicas, metodología). General, cross-engagement, DATO inerte.
- `rag/context/` (ESTE) — QUÉ SABEMOS YA DE ESTE OBJETIVO. **Per-engagement, EFÍMERO, EN-ZONA**: el store
  vive bajo `engagements/<id>/context.db` (zona E3, datos de cliente, gitignored) y NUNCA se mezcla con el
  RAG de conocimiento. Indexa los artefactos ACUMULADOS del propio engagement (recon/evidence/notes) para
  que los agentes pregunten "¿qué se sabe ya de este endpoint/host?" sin releer todo el blackboard.

Este módulo es SOLO stdlib (como scope_guard/redactor) y NO importa torch/embeddings: aquí vive la lógica
crítica de AISLAMIENTO (CONSTITUTION §1 — un engagement jamás ve el contexto de otro), testeable sin el venv.
"""
import os

# Artefactos que SÍ se indexan (salida acumulada del engagement) y los que NUNCA (material crudo).
INDEXABLE_SUBDIRS = ("recon", "exploit", "evidence", "notes")
# `loot/` contiene credenciales/secretos CRUDOS del cliente (referenciados por secret_ref): NO se indexa.
# DEFENSA EN PROFUNDIDAD: además de excluir loot/, el ingester pasa CADA chunk por `redactor.redact()` antes
# de embeber/guardar, así que un secreto en claro que se colara en recon/evidence/notes NO acaba ni en el
# vector ni en la columna de texto del store (ver ingest_context.py). El store es además en-zona + gitignored.
EXCLUDED_SUBDIRS = ("loot",)
INDEX_EXTS = (".md", ".txt", ".log", ".json", ".csv", ".nmap", ".gnmap")

DB_NAME = "context.db"


def _safe_id(engagement_id):
    """Un engagement_id es una ETIQUETA, no una ruta. Rechaza vacío, '.', '..' y cualquier separador de
    ruta o byte nulo (anti path-traversal). Devuelve el id validado o lanza ValueError."""
    if not engagement_id or not isinstance(engagement_id, str):
        raise ValueError("engagement_id vacío")
    # Un id es una ETIQUETA: sin separadores de ruta, ni ':' (drive/ADS de Windows: D:x, foo:bar), ni nulo.
    if engagement_id in (".", "..") or any(c in engagement_id for c in ("/", "\\", ":", "\0")):
        raise ValueError(f"engagement_id inseguro (parece una ruta, no una etiqueta): {engagement_id!r}")
    return engagement_id


def engagement_dir(repo_root, engagement_id, *, create=False):
    """Directorio ABSOLUTO del engagement, validado DENTRO de engagements/ (defensa en profundidad:
    aunque el id pase _safe_id, la ruta resuelta debe quedar bajo engagements/)."""
    _safe_id(engagement_id)
    engagements_root = os.path.realpath(os.path.join(repo_root, "engagements"))
    raw = os.path.join(engagements_root, engagement_id)
    # El directorio del engagement NO puede ser un symlink: uno intra-zona (ENG-A -> ENG-B) pasaría el check
    # de commonpath y cruzaría a otro engagement; uno hacia fuera se resolvería fuera. Prohibirlo cierra ambos.
    if os.path.islink(raw):
        raise ValueError(f"el directorio del engagement no puede ser un symlink: {engagement_id!r}")
    eng_dir = os.path.realpath(raw)
    if os.path.commonpath([engagements_root, eng_dir]) != engagements_root or eng_dir == engagements_root:
        raise ValueError(f"ruta fuera de la zona engagements/: {eng_dir}")
    if create:
        os.makedirs(eng_dir, exist_ok=True)
    return eng_dir


def context_db_path(repo_root, engagement_id, *, create=False):
    """Ruta ABSOLUTA del store de contexto de ESTE engagement: engagements/<id>/context.db. Garantiza el
    aislamiento: NUNCA devuelve una ruta en rag/knowledge ni fuera de la zona (lo impone engagement_dir)."""
    return os.path.join(engagement_dir(repo_root, engagement_id, create=create), DB_NAME)


def iter_indexable_files(repo_root, engagement_id):
    """Genera (subdir, ruta_absoluta) de los artefactos INDEXABLES del engagement (recon/exploit/evidence/
    notes), NUNCA loot/. Solo extensiones de texto. Ignora el propio context.db y ficheros ocultos."""
    base = engagement_dir(repo_root, engagement_id)
    for sub in INDEXABLE_SUBDIRS:
        root = os.path.join(base, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # poda defensiva: jamás desciendas a un loot/ anidado
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_SUBDIRS and not d.startswith(".")]
            for fn in sorted(filenames):
                if fn.startswith(".") or fn == DB_NAME:
                    continue
                if os.path.splitext(fn)[1].lower() in INDEX_EXTS:
                    yield sub, os.path.join(dirpath, fn)
