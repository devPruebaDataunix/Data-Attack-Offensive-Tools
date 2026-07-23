#!/usr/bin/env python3
"""
steering.py — PILOTAJE INTERACTIVO del engagement en marcha (mejora v2.61; idea de strix, Apache-2.0 →
reimplementación limpia, solo stdlib). Un canal por el que el OPERADOR (o el dashboard) inyecta
DIRECTIVAS que el Orquestador recoge en los *seams* del engagement (entre delegaciones — el Task tool es
síncrono, no se interrumpe un subagente a media ejecución) y aplica: repriorizar un host/vector, pausar/
reanudar, abortar un vector, dar una pista, o SUBIR la supervisión. Sin reiniciar el engagement.

Las directivas viven en `engagements/<id>/control/steering.json` (fuera del blackboard que escriben los
agentes: es el canal del OPERADOR, como `scope.json`). El hook `steering_nudge.py` (C23) recuerda al
Orquestador las `pending` tras cada delegación.

Seguridad (innegociable):
- **Una directiva NUNCA relaja una puerta.** No puede ampliar scope, permitir daño, ni BAJAR el
  `approval_mode`. `enqueue` RECHAZA cualquier tipo no permitido; `raise-approval` solo ENDURECE (a un
  nivel más estricto que el actual). Y aunque una directiva maliciosa se colara, los hooks deterministas
  (`scope_guard`/`approval_gate`) corren FUERA del prompt y no se pueden desactivar desde aquí — la
  directiva es DATO que el Orquestador lee, no una orden que salte las guardas (CONSTITUTION §1/§2).
- **Confinado al engagement.** El `engagement_id` se sanea (sin separadores/`..`); el fichero vive bajo
  `engagements/<id>/control/`. Escritura ATÓMICA (reusa `blackboard.atomic_write_json`).

Uso:
    python tools/steering.py add --type focus --target t-dmz --note "prioriza el Citrix"
    python tools/steering.py add --type raise-approval --to full
    python tools/steering.py list [--pending]
    python tools/steering.py ack --id S-001 [--outcome applied|rejected|skipped] [--note "..."]
"""
import argparse
import contextlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")

sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from blackboard import atomic_write_json  # noqa: E402  (escritura atómica compartida)
try:
    from scope_guard import load_scope
except Exception:  # noqa: BLE001
    load_scope = None

# Directivas de PILOTAJE permitidas. NO incluyen nada que relaje una puerta (no hay 'add-scope',
# 'disable-guard' ni 'lower-approval'): un tipo fuera de esta lista se RECHAZA en enqueue.
ALLOWED_TYPES = {"focus", "deprioritize", "skip", "pause", "resume", "abort-vector", "hint",
                 "raise-approval", "escalate"}
OUTCOMES = {"applied", "rejected", "skipped"}
# Estrictitud de la supervisión: full (máx) > critical > auto (mín). raise-approval solo sube.
_STRICTNESS = {"auto": 0, "critical": 1, "full": 2}


def _safe_eid(eid):
    """Sanea el engagement_id para construir rutas (sin separadores ni `..`)."""
    base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(str(eid or "engagement")))
    # `.` está permitido (nombres tipo `acme.com`), pero un componente que sea SOLO puntos
    # (`.`, `..`, `...`) es directorio-actual/traversal → lo neutralizamos: `basename` ya impide
    # bajar más de un nivel, pero `..` escaparía de engagements/ (confinamiento, CONSTITUTION §1).
    if base.strip(".") == "":
        return "engagement"
    return base


def _control_path(eid):
    return os.path.join(ROOT, "engagements", _safe_eid(eid), "control", "steering.json")


@contextlib.contextmanager
def _locked(eid):
    """Lock por-engagement alrededor del read-modify-write. Evita el lost-update cuando el operador y
    el dashboard escriben a la vez (`atomic_write_json` no corrompe el fichero, pero sí perdería la
    directiva del que escribe segundo). Lockfile `O_EXCL` con reintentos; best-effort (si no se
    adquiere en ~5s, procede igual en vez de bloquear el pilotaje). Stdlib, cross-platform."""
    lockp = _control_path(eid) + ".lock"
    os.makedirs(os.path.dirname(lockp), exist_ok=True)
    fd = None
    for _ in range(100):  # ~5s (100 × 50ms)
        try:
            fd = os.open(lockp, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(lockp)


def current_engagement_id():
    if os.path.isfile(ENGAGEMENT):
        try:
            with open(ENGAGEMENT, encoding="utf-8") as f:
                return json.load(f).get("engagement_id") or "engagement"
        except Exception:  # noqa: BLE001
            pass
    return "engagement"


def _load(eid):
    p = _control_path(eid)
    if os.path.isfile(p):
        data = None
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001  JSON ilegible/parcial
            # NO reseteamos en silencio (perderíamos directivas y las sobrescribiríamos): apartamos
            # el fichero dañado para inspección y arrancamos limpio con aviso por stderr.
            try:
                os.replace(p, p + ".corrupt")
                print(f"steering: {p} ilegible → apartado a {p}.corrupt", file=sys.stderr)
            except OSError:
                pass
        if isinstance(data, dict) and isinstance(data.get("directives"), list):
            # Filtra elementos no-dict (robustez del read-path: pending/list no deben romper).
            data["directives"] = [d for d in data["directives"] if isinstance(d, dict)]
            return data
    return {"engagement_id": _safe_eid(eid), "directives": []}


def _next_id(directives):
    """Siguiente id `S-NNN` derivado del MÁXIMO existente, no de `len` — robusto ante poda o edición
    externa del fichero (con `len` una directiva borrada haría que el siguiente id COLISIONARA)."""
    mx = 0
    for d in directives:
        m = re.match(r"S-(\d+)$", str(d.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return f"S-{mx + 1:03d}"


def _approval_mode():
    """approval_mode vigente (de scope.json → constraints), def. 'critical'."""
    try:
        s = load_scope() if load_scope else None
        m = ((s or {}).get("constraints", {}) or {}).get("approval_mode")
        return m if m in _STRICTNESS else "critical"
    except Exception:  # noqa: BLE001
        return "critical"


def validate(directive):
    """(ok, motivo). Rechaza tipos que relajarían una puerta y `raise-approval` que no ENDUREZCA."""
    t = directive.get("type")
    if t not in ALLOWED_TYPES:
        return False, (f"tipo '{t}' no permitido: una directiva de pilotaje no puede relajar scope/"
                       f"no-daño/aprobación. Permitidos: {sorted(ALLOWED_TYPES)}")
    if t == "raise-approval":
        to = directive.get("to")
        if to not in _STRICTNESS:
            return False, f"raise-approval requiere 'to' en {sorted(_STRICTNESS)}"
        cur = _approval_mode()
        if _STRICTNESS[to] <= _STRICTNESS[cur]:
            return False, (f"raise-approval solo ENDURECE: '{to}' no es más estricto que el actual "
                           f"'{cur}' (bajar la supervisión no se permite).")
    return True, ""


def enqueue(eid, type_, target=None, note=None, to=None):
    """Añade una directiva 'pending' (tras validar que NO relaja ninguna puerta). Devuelve la directiva."""
    d = {"type": type_, "status": "pending",
         "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if target:
        d["target"] = target
    if note:
        d["note"] = note
    if to:
        d["to"] = to
    ok, why = validate(d)
    if not ok:
        raise ValueError(why)
    with _locked(eid):
        state = _load(eid)
        d["id"] = _next_id(state["directives"])
        state["directives"].append(d)
        os.makedirs(os.path.dirname(_control_path(eid)), exist_ok=True)
        atomic_write_json(_control_path(eid), state)
    return d


def pending(eid):
    """Directivas `pending` con un tipo PERMITIDO. Filtrar por `ALLOWED_TYPES` endurece el READ-path:
    una directiva con tipo relajante (`lower-approval`/`disable-guard`/`add-scope`) plantada
    DIRECTAMENTE en el fichero (saltándose `enqueue`, que la rechazaría) nunca llega al prompt del
    Orquestador vía el nudge — defensa en profundidad (los gates deterministas mandan igualmente)."""
    return [d for d in _load(eid).get("directives", [])
            if d.get("status") == "pending" and d.get("type") in ALLOWED_TYPES]


def ack(eid, directive_id, outcome="applied", note=None):
    """Marca una directiva como applied/rejected/skipped. Devuelve la directiva o lanza KeyError."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome debe ser uno de {sorted(OUTCOMES)}")
    with _locked(eid):
        state = _load(eid)
        for d in state.get("directives", []):
            if d.get("id") == directive_id:
                d["status"] = outcome
                d["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if note:
                    d["ack_note"] = note
                atomic_write_json(_control_path(eid), state)
                return d
    raise KeyError(f"no existe la directiva '{directive_id}'")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pilotaje interactivo del engagement (directivas del operador).",
                                 allow_abbrev=False)
    ap.add_argument("--engagement", default=None, help="engagement_id (def.: el del blackboard).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="añade una directiva de pilotaje.")
    a.add_argument("--type", required=True, choices=sorted(ALLOWED_TYPES))
    a.add_argument("--target", default=None, help="target_id / vector al que aplica (si procede).")
    a.add_argument("--note", default=None, help="texto/pista para el Orquestador.")
    a.add_argument("--to", default=None, help="para raise-approval: nivel más estricto (critical/full).")
    lst = sub.add_parser("list", help="lista las directivas.")
    lst.add_argument("--pending", action="store_true", help="solo las pendientes.")
    ackp = sub.add_parser("ack", help="marca una directiva como aplicada/rechazada/omitida.")
    ackp.add_argument("--id", required=True)
    ackp.add_argument("--outcome", default="applied", choices=sorted(OUTCOMES))
    ackp.add_argument("--note", default=None)
    args = ap.parse_args(argv)

    eid = args.engagement or current_engagement_id()
    try:
        if args.cmd == "add":
            d = enqueue(eid, args.type, args.target, args.note, args.to)
            print(json.dumps(d, ensure_ascii=False))
        elif args.cmd == "list":
            items = pending(eid) if args.pending else _load(eid).get("directives", [])
            print(json.dumps(items, ensure_ascii=False, indent=2))
        elif args.cmd == "ack":
            print(json.dumps(ack(eid, args.id, args.outcome, args.note), ensure_ascii=False))
    except ValueError as e:
        print(f"steering: {e}", file=sys.stderr)
        return 3
    except KeyError as e:
        print(f"steering: {e}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
