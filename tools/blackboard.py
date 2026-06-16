#!/usr/bin/env python3
"""
blackboard.py — Utilidades deterministas para el blackboard (contracts/engagement.json).

Dos funciones, solo stdlib (mismo criterio que scope_guard.py — sin dependencias):

- atomic_write_json(path, data): escribe JSON de forma ATÓMICA (tmp + os.replace) para que
  ninguna escritura quede a medias si el proceso se corta o dos escritores coinciden.
- validate_engagement(data, contracts_dir): comprueba los campos OBLIGATORIOS de cada objeto
  del blackboard (engagement / target / finding + lessons/evidence anidados) contra los
  esquemas en contracts/*.schema.json. Devuelve una lista de violaciones (vacía = OK).
  No valida tipos ni enums: solo PRESENCIA de campos requeridos, que es la fisura real de
  los handoffs entre agentes.
"""
import json
import os
import tempfile

CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")


def atomic_write_json(path, data, indent=2):
    """Escribe `data` como JSON en `path` de forma atómica (tmp en el mismo dir + os.replace)."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atómico dentro del mismo filesystem
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _required(schema_path):
    try:
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f).get("required", [])
    except Exception:
        return []


def _nested_required(engagement_schema_path, key):
    """`required` de los items de un array anidado (lessons / evidence) en engagement.schema."""
    try:
        with open(engagement_schema_path, encoding="utf-8") as f:
            props = json.load(f).get("properties", {})
        return props.get(key, {}).get("items", {}).get("required", [])
    except Exception:
        return []


def validate_engagement(data, contracts_dir=CONTRACTS):
    """Devuelve la lista de violaciones de campos obligatorios. Lista vacía = válido."""
    if not isinstance(data, dict):
        return ["engagement.json no es un objeto JSON"]

    eng_schema = os.path.join(contracts_dir, "engagement.schema.json")
    eng_req = _required(eng_schema)
    tgt_req = _required(os.path.join(contracts_dir, "target.schema.json"))
    fnd_req = _required(os.path.join(contracts_dir, "finding.schema.json"))
    les_req = _nested_required(eng_schema, "lessons")
    evd_req = _nested_required(eng_schema, "evidence")

    violations = []
    for k in eng_req:
        if k not in data:
            violations.append(f"engagement: falta campo obligatorio '{k}'")

    def _check_list(items, req, label, id_key):
        if not isinstance(items, list):
            return
        for i, obj in enumerate(items):
            if not isinstance(obj, dict):
                violations.append(f"{label}[{i}]: no es un objeto")
                continue
            ident = obj.get(id_key, f"#{i}")
            missing = [k for k in req if k not in obj]
            if missing:
                violations.append(f"{label} {ident}: faltan {missing}")

    _check_list(data.get("targets", []), tgt_req, "target", "target_id")
    _check_list(data.get("findings", []), fnd_req, "finding", "finding_id")
    _check_list(data.get("lessons", []), les_req, "lesson", "lesson_id")
    _check_list(data.get("evidence", []), evd_req, "evidence", "ts")
    return violations
