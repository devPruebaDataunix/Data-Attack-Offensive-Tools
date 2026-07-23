# skilltrain — optimizador de skills (SkillOpt) · LAB-ONLY · build-time

Optimiza el **texto de metodología de una skill** (`plugin/skills/<name>/SKILL.md`) para subir el close-rate
autónomo del motor en el eval-harness (`benchmark/`), **sin reentrenar el modelo**. Idea: `microsoft/SkillOpt`
(optimización en espacio de texto para LLM congelado). Es el complemento de ENTRENAMIENTO de la mejora E
(el eval-harness MIDE; SkillOpt MEJORA). Produce un `skilltrain/out/best_skill.md` **candidato** — NUNCA se
auto-aplica.

> **LAB-ONLY, build-time.** No forma parte del runtime del producto. `build_plugin.py` NO incluye `skilltrain/`.
> No toca datos de cliente (una skill es técnica generalizada, zona E3).

## Bucle (rollout → reflect → aggregate → select → update → evaluate)
1. **baseline** — puntúa la skill actual sobre el split `heldout`.
2. **rollout** — corre engagements sobre el split `train` con la skill vigente; recoge transcripts + veredictos.
3. **reflect** — un LLM analiza los FALLOS y propone ediciones de la skill (candidatos).
4. **score+select** — puntúa los candidatos sobre `train`; se queda el mejor.
5. **update** — adopta el mejor candidato.
6. **evaluate (GATE)** — puntúa sobre `heldout` (nunca visto en el bucle). Acepta solo si `heldout` MEJORA
   (anti-overfit). Escribe `out/best_skill.md`.

`reflect` y `rollout` lanzan modelo/agente → se ejecutan en **Kali** (labs vivos + provider). Aquí (build-time)
están como *seams* explícitos (`optimize.py` los inyecta); `--dry-run` enseña el plan completo sin ejecutarlos.

## Piezas
- `config.example.json` — skill objetivo, `train`/`heldout` (del propio eval-harness), `k` (pass@k),
  presupuesto (`max_iters`), `provider` (`claude` | `opencode`).
- `guard.py` — **lint de gobernanza determinista** de un candidato: rechaza texto que intente
  desactivar/eludir scope/approval/hooks (o `--yolo`/`--dangerously-skip-permissions`), o que meta datos de
  cliente. Un candidato que no pasa el lint se descarta ANTES de puntuarse.
- `scorer.py` — **envuelve `benchmark/run_gate.py` con `--canary` OBLIGATORIO**. `eval_is_canary_capable`
  exige bloque `canary` (single) o `canary.per_host` (multi_host); si un eval no lo tiene, el scorer **se
  niega a puntuarlo** (HARD-GATE anti-reward-hack). Reward = pass@k sobre evidencia anclada al canario.
- `apply_skill.py` — intercambio ATÓMICO de la SKILL.md candidata + restauración en `finally` (patrón de
  `run_gate` con `scope.json`). Nunca deja la skill real modificada.
- `optimize.py` — orquesta el bucle; `--dry-run` imprime el plan. Escribe solo en `skilltrain/out/`.

## Gobernanza (innegociable — cableada, no opcional)
- **Reward = impacto/proof/ROE-scope, NUNCA "menos safeguards".** El scorer solo ve el PASS **canario**; no
  existe término de recompensa por menos aprobaciones/scope. (Evasión OBLITERATUS rechazada; ver
  memoria `safeguard-not-a-selection-criterion`.)
- **Suelo de seguridad:** los hooks deterministas (`scope_guard`/`approval_gate`) corren FUERA del prompt →
  una skill optimizada NO puede desactivarlos. El optimizer solo edita texto de metodología; confinado a
  `skilltrain/out/` + la copia sandbox de la skill (no toca `.claude/`, `contracts/`, hooks).
- **Solo el canario cuenta:** un PASS sin `--canary` (constante conocida) NO es señal de recompensa válida.
- **Humano + council** antes de desplegar cualquier `out/best_skill.md` a `plugin/skills/`. No auto-apply.

## Evaluación de integración — puntos muertos cerrados
| Riesgo | Cómo se cierra |
|--------|----------------|
| Reward-hacking del optimizer | `scorer` exige `--canary`; si el eval no es canary-capable, se niega a puntuar (no hay señal forjable). |
| Skill que intente relajar puertas | `guard.py` la rechaza en lint; y aunque se colara, los hooks mandan fuera del prompt. |
| Overfit a pocos labs | GATE en `heldout` (nunca visto) + acepta solo si mejora; documentar que hacen falta más labs. |
| Coste de rollouts | `provider: opencode` + NVIDIA free (LAB); `claude` CLI para el GATE. Cloud nunca E2/cliente. |
| Contaminación del runtime | `skilltrain/` es build-time; `build_plugin.py` no lo empaqueta. `out/` gitignored. |
| Mutación fuera de zona | El optimizer solo escribe en `out/`; `apply_skill` restaura la skill real en `finally`. |

## Estado
Andamiaje + gobernanza + partes deterministas (guard/scorer-gate/apply_skill/plan) **implementadas y
testeadas** (`test_skilltrain.py`). Los seams `rollout`/`reflect` (lanzan modelo/agente contra labs) se
**verifican en Kali** — aquí `--dry-run` enseña el plan. Prerrequisito cumplido: el canario (`--canary`,
v2.63/v2.64) ya da la señal anti-reward-hack; SkillOpt **solo** consume PASS canario.
