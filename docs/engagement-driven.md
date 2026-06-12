# Flujo "Engagement-Driven" (spec-driven adaptado a ofensiva)

Adaptación de la metodología **Spec-Driven Development** de [GitHub Spec Kit](https://github.com/github/spec-kit)
al dominio de un engagement de seguridad ofensiva. No usamos su CLI ni su andamiaje: tomamos **el
patrón** (definir y gobernar antes de ejecutar, y auditar la coherencia entre artefactos).

## La idea
Igual que SDD define la *especificación* antes de escribir código, aquí definimos el **gobierno y el
brief** antes de tocar un objetivo, y **auditamos la coherencia** antes de reportar. El "qué" y las
reglas van por delante del "cómo".

## El flujo y su equivalencia

| Paso (spec-kit) | Aquí | Artefacto |
| :--- | :--- | :--- |
| `constitution` | Principios innegociables del engagement | **`CONSTITUTION.md`** |
| `specify` | Brief del engagement (objetivos, alcance, ROE) | **`templates/engagement-spec.md`** |
| `clarify` | Resolver lo no definido (lo hace el bot: *pregunta el scope*) | `bot/intel/scope.py` |
| `plan` | Playbook de orquestación hub-and-spoke | `AGENTS.md` |
| `tasks` | Fases del engagement → agentes | modelo de fases + blackboard |
| `implement` | Los agentes ejecutan (con gate de scope + aprobación humana) | `.claude/agents/` |
| `analyze` | **Auditoría de coherencia** antes de cerrar | **`tools/analyze_engagement.py`** |
| (informe) | Redacción profesional humanizada | `reporting` + `templates/report-template.md` |

## Orden de trabajo
1. **Constitución** — lee/respeta `CONSTITUTION.md` (es ley; prevalece sobre todo).
2. **Brief** — rellena `templates/engagement-spec.md` con el cliente (objetivos, alcance, ROE).
3. **Materializa el alcance** — `contracts/scope.json` (lo que `scope_guard.py` aplica). Debe
   coincidir con el §3 del brief.
4. **Clarifica** — si falta alcance, el bot pregunta en vez de adivinar.
5. **Ejecuta** — el Orquestador (`AGENTS.md`) delega por fases; cada acción contra el target pasa
   por el gate de scope y la aprobación humana.
6. **Analiza** — `python tools/analyze_engagement.py` antes de reportar; resuelve incongruencias.
7. **Reporta** — `reporting` genera el informe solo con hallazgos confirmados y con evidencia.

## Qué tomamos de Spec Kit y qué NO

**Adoptado (adaptado):**
- La **constitución** como gobierno versionado del que dependen todas las decisiones.
- El **brief/spec** explícito previo a la ejecución (separar "qué/por qué" de "cómo").
- El **`/analyze`** de coherencia entre artefactos (la pieza de más valor para evitar informes con
  incongruencias).

**NO adoptado (no encaja en un repo ofensivo, añadiría incongruencia):**
- El CLI `specify` y el andamiaje `.specify/` (init, extensions, presets, overrides): orientados a
  proyectos de software, no a engagements.
- Artefactos de desarrollo: `data-model.md`, `research.md`, `contracts/` de API, `quickstart.md`,
  `/implement`, `/taskstoissues` (issues de GitHub violan el NDA de un engagement).
- Su modelo de "feature branches" por especificación.

> En resumen: importamos la **disciplina** (gobernar y especificar antes de ejecutar, auditar antes
> de cerrar), no la **maquinaria** de desarrollo de software.
