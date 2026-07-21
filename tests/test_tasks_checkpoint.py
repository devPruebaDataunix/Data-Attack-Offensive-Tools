#!/usr/bin/env python3
"""Tests de B (Shannon) — checkpoint por-tarea + reanudación.

Cubre:
- `tasks[]` en engagement.schema.json: propiedad presente, `required` correcto, enum de `status`.
- Validación jsonschema del subesquema de un item de tarea (válido / inválido) — sin $ref, sin resolver.
- AGENTS.md declara la regla dura (Task síncrono / no-background) y la sección de reanudación con tasks[].
- El menú del bot expone `/resume` (defensa: además el test_botfmt exige que sea @authorized).

Sin pytest: asserts planos, `python tests/test_tasks_checkpoint.py` (sale 1 si algo falla).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def t_schema():
    sch = json.loads(_load("contracts/engagement.schema.json"))
    tasks = sch["properties"].get("tasks")
    check("engagement.schema tiene 'tasks'", tasks is not None)
    if not tasks:
        return
    item = tasks["items"]
    check("tasks.items.required = task_id/agent/objective/status",
          set(item["required"]) == {"task_id", "agent", "objective", "status"})
    enum = item["properties"]["status"]["enum"]
    check("status enum = pending/running/done/failed/skipped",
          set(enum) == {"pending", "running", "done", "failed", "skipped"})
    check("tasks NO está en required (retrocompatible)", "tasks" not in sch.get("required", []))
    check("tiene campo opcional 'notes' (R7 council)", "notes" in item["properties"])

    # Validación jsonschema del subesquema del item (aislado: sin $ref -> sin resolver).
    try:
        import jsonschema
    except Exception:
        print("  (jsonschema ausente: se omite la validación estructural)")
        return
    valid = {"task_id": "T-001", "agent": "web-exploit", "objective": "probar IDOR en /api/users",
             "status": "running", "phase": "exploitation", "attempts": 1,
             "output_ref": "engagements/E1/exploit/idor.json"}
    try:
        jsonschema.validate(valid, item)
        check("item de tarea VÁLIDO valida", True)
    except jsonschema.ValidationError as e:
        check(f"item de tarea VÁLIDO valida ({e.message})", False)
    bad = dict(valid, status="background")  # status inventado -> debe fallar
    try:
        jsonschema.validate(bad, item)
        check("status inválido 'background' RECHAZADO", False)
    except jsonschema.ValidationError:
        check("status inválido 'background' RECHAZADO", True)
    missing = {"task_id": "T-002", "agent": "nuclei"}  # falta objective/status
    try:
        jsonschema.validate(missing, item)
        check("item sin campos obligatorios RECHAZADO", False)
    except jsonschema.ValidationError:
        check("item sin campos obligatorios RECHAZADO", True)


def t_agents_md():
    md = _load("AGENTS.md")
    check("AGENTS.md: Task tool SÍNCRONO", "Task tool es SÍNCRONO" in md)
    check("AGENTS.md: prohíbe background", "segundo plano" in md and "background" in md)
    check("AGENTS.md: sección de reanudación con tasks[]",
          "Ejecución síncrona y reanudación" in md and "tasks[]" in md)
    check("AGENTS.md: no re-ejecutar done NI skipped al reanudar",
          "NO re-ejecutes" in md and "ni las `skipped`" in md)
    check("AGENTS.md: la reanudación no relaja puertas",
          "no relaja ninguna puerta" in md.lower() or "re-valida scope" in md)
    # Reservas del council aplicadas:
    check("R5 artefacto manda (degrada done sin output_ref)", "degrádala a `failed`" in md)
    check("R4 no replay ciego (spray/C2)", "replay ciego" in md and "lockout" in md)
    check("R6 respeta depends_on al reanudar", "`depends_on` no esté `done`" in md)
    check("R3 regla no-background acotada al Task-tool del Orquestador",
          "Task-tool del Orquestador" in md and "hospeda" in md)
    check("R2 entrega A2A que es delegación se registra en tasks[]",
          "una entrega A2A es una delegación" in md)


def t_menu_resume():
    sys.path.insert(0, os.path.join(ROOT, "bot"))
    import botfmt as B
    cmds = [c for c, _ in B.command_menu()]
    check("/resume en el menú del bot", "resume" in cmds)


if __name__ == "__main__":
    print("== schema tasks[] =="); t_schema()
    print("== AGENTS.md reglas =="); t_agents_md()
    print("== menú /resume =="); t_menu_resume()
    print()
    if _fail:
        print(f"FALLOS: {len(_fail)} -> {_fail}")
        sys.exit(1)
    print("TODOS OK")
