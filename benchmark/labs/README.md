# benchmark/labs — apps vulnerables de laboratorio (verticales bug bounty)

Targets **deliberadamente vulnerables** para validar las verticales WEB/API del motor de forma
reproducible (evals en `benchmark/evals/*.json`, graduador `run_eval.py` con `success_criteria.type`
`web`/`api`).

> ⚠️ **LAB-ONLY, AISLADO.** Estas apps son vulnerables a propósito. Levántalas **solo** en una VM/red
> aislada (loopback), **nunca** expuestas a Internet ni en una máquina con datos reales. El graduador
> `run_gate.py` **rechaza** targets que no sean de laboratorio.

## WEB — Juice Shop + DVWA (compose de una pieza)

```bash
docker compose -f benchmark/labs/docker-compose.yml up -d
# Juice Shop -> http://127.0.0.1:3000   (eval: juice-shop)
# DVWA       -> http://127.0.0.1:4280   (eval: dvwa; /setup.php -> Create DB, Security = Low)
python benchmark/run_gate.py --eval juice-shop     # lanza + gradúa (LAB-ONLY)
docker compose -f benchmark/labs/docker-compose.yml down -v   # desechable
```

## API — crAPI (stack upstream)

crAPI ("completely ridiculous API") necesita ~6 servicios (API, web, mongo, postgres, mailhog…), así
que se trae de su **compose upstream** en vez de duplicarlo aquí (evita drift de versiones):

```bash
curl -o /tmp/crapi.yml https://raw.githubusercontent.com/OWASP/crAPI/main/deploy/docker/docker-compose.yml
docker compose -f /tmp/crapi.yml up -d          # web/API en http://127.0.0.1:8888
python benchmark/run_gate.py --eval crapi        # eval: crapi (necesita >=2 identidades en identities[])
docker compose -f /tmp/crapi.yml down -v
```

## Qué valida cada eval

| Eval | Vertical | PASS (proof-by-exploitation) |
|------|----------|------------------------------|
| `juice-shop` | WEB | ≥2 findings **CONFIRMED** cubriendo A01 (control de acceso) + A03 (inyección) |
| `dvwa` | WEB | ≥2 findings **CONFIRMED** de inyección A03 (SQLi + command injection) |
| `crapi` | API | ≥2 findings **CONFIRMED** cubriendo API1:2023 (BOLA) + API3:2023 (BOPLA) con arnés diferencial |

El criterio `web`/`api` mide sobre `findings[]` del blackboard: exige **CONFIRMED** (no basta candidato)
y **cobertura OWASP por clase** (`require_owasp`). Es la disciplina proof-by-exploitation aplicada al
banco de pruebas.
