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

## Pendiente de cableado
- Auto-lanzar el engagement desde el harness (hoy gradúa lo ya ejecutado).
- Graders adicionales: cobertura de fases, tiempo-a-root, coste, model-grader de calidad del informe.
- Suite "gauntlet": fácil → medio → difícil, con pass@k por máquina.

> `results.jsonl` está gitignored (datos de runtime).
