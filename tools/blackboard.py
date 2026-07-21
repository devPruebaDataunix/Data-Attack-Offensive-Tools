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
    msg_req = _required(os.path.join(contracts_dir, "a2a-message.schema.json"))
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
    _check_list(data.get("messages", []), msg_req, "message", "message_id")
    _check_list(data.get("lessons", []), les_req, "lesson", "lesson_id")
    _check_list(data.get("evidence", []), evd_req, "evidence", "ts")

    # Invariante white-box (Shannon "A"): una HIPÓTESIS de code-recon (finding con `code_ref`) es un
    # LEAD del código, no una prueba. NO puede marcarse `confirmed`/`exploited` sin corroboración
    # DINÁMICA capturada en `evidence` — el código solo no confirma nada (§3). Enforcement determinista
    # a la espera del proof-state completo (Shannon "F").
    findings = data.get("findings", [])
    if isinstance(findings, list):
        for i, f in enumerate(findings):
            if not isinstance(f, dict):
                continue
            if f.get("code_ref") and f.get("status") in ("confirmed", "exploited"):
                if not (f.get("evidence") or "").strip():
                    ident = f.get("finding_id", f"#{i}")
                    violations.append(
                        f"finding {ident}: es una hipótesis white-box (tiene `code_ref`) marcada "
                        f"'{f.get('status')}' SIN `evidence` — el código es un LEAD, no una prueba: "
                        f"exige corroboración dinámica capturada antes de confirmar (déjalo 'candidate').")
    return violations


# ── Bus A2A mediado (helpers deterministas) ────────────────────────────────────
# Un agente NO invoca a otro: deja un mensaje en messages[] y el Orquestador-router lo
# entrega. Estos helpers son solo stdlib y no escriben a disco por sí mismos (usa
# atomic_write_json para persistir). El techo de hops lo APLICA a2a_guard.py (C15).
DEFAULT_MAX_A2A_HOPS = 50


def a2a_hop_ceiling(scope):
    """Techo de saltos A2A por engagement. Sale de scope.constraints.max_a2a_hops si es un int>0,
    si no DEFAULT_MAX_A2A_HOPS. `scope` es el dict de scope.json (o None)."""
    try:
        c = (scope or {}).get("constraints", {}).get("max_a2a_hops")
        if isinstance(c, int) and c > 0:
            return c
    except Exception:
        pass
    return DEFAULT_MAX_A2A_HOPS


def pending_messages(data, to_agent=None):
    """Mensajes con status 'pending' (o sin status) del blackboard, opcionalmente filtrados
    por destinatario. Devuelve una lista (no muta `data`)."""
    out = []
    for m in (data or {}).get("messages", []):
        if not isinstance(m, dict):
            continue
        if m.get("status", "pending") != "pending":
            continue
        if to_agent is not None and m.get("to_agent") != to_agent:
            continue
        out.append(m)
    return out


def set_message_status(data, message_id, status):
    """Fija el status de un mensaje por message_id. Devuelve True si lo encontró. Muta `data`."""
    for m in (data or {}).get("messages", []):
        if isinstance(m, dict) and m.get("message_id") == message_id:
            m["status"] = status
            return True
    return False
