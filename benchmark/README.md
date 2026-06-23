# benchmark — eval-harness / GATE de capacidad

Mide **objetivamente** si Data Attack cierra un objetivo de forma **autónoma** (EDD + pass@k). Inspirado
en el `eval-harness` de ECC, adaptado a engagements ofensivos.

## Cómo funciona
1. Un **eval** (`evals/*.json`) define `target`, `difficulty` y `success_criteria` (p.ej. prueba de root
   por regex sobre la evidencia + nº mínimo de findings).
2. Lanzas el engagement (manual/externo, p.ej. `ORCH_APPROVAL_MODE=auto claude` contra el target).
3. `run_eval.py` **gradúa** el resultado inspeccionando `contracts/engagement.json` + la evidencia, y
   registra **pass@k**.

```bash
python benchmark/run_eval.py --list
python benchmark/run_eval.py --eval dockerlabs-injection --engagement contracts/engagement.json --record
```

## El GATE del proyecto
`linux-hard-gate` es la barrera: **PASS autónomo end-to-end en una máquina DockerLabs "Difícil" de
servidor Linux crítico** = capacidad verificada. Hasta lograrlo, el resto de trabajo (p.ej. el trailer)
permanece supeditado a este resultado.

## Auto-lanzar el GATE (`run_gate.py`)
`run_gate.py` **LANZA** el engagement end-to-end contra un **lab** y lo gradúa (antes había que lanzarlo a
mano): escribe un `scope.json` acotado (`approval_mode=auto`), crea `engagements/GATE-<id>/`, arranca el
Orquestador headless y gradúa con pass@k. **LAB-ONLY** (rechaza targets que no sean de laboratorio);
respalda y restaura tu `scope.json`.

```bash
python benchmark/run_gate.py --eval dockerlabs-injection             # target del propio eval
python benchmark/run_gate.py --eval linux-hard-gate --target 10.10.11.20 --record
python benchmark/run_gate.py --eval dockerlabs-injection --dry-run   # enseña el plan, no lanza
```
`--dry-run` no toca nada; `--yolo` añade `--dangerously-skip-permissions` (lab desatendido). Verifica la
cobertura del RAG de técnicas antes de un run con `python rag/knowledge/query_kb.py --stats`.

## Pendiente de cableado
- Graders adicionales: cobertura de fases, tiempo-a-root, coste, model-grader de calidad del informe.
- Suite "gauntlet": fácil → medio → difícil, con pass@k por máquina.

> `results.jsonl` está gitignored (datos de runtime).
