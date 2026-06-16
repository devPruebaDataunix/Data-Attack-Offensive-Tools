# Propuestas de tuning de prompts (tras el routing a Opus 4.8)

> **Estado: PROPUESTAS — NO aplicadas.** La guía oficial de migración de modelos dice que los
> cambios de system-prompt se proponen, no se aplican a ciegas. Aquí tienes cambios concretos,
> cada uno con su porqué; acepta/rechaza uno a uno. Ninguno toca código ni lógica, solo texto de
> instrucción de agentes.

## Por qué ahora
El routing puso `web-exploit`/`post-exploit`, `ai-security` y `reporting` en **Opus 4.8** (antes
Fable). (`network-exploit` también estuvo en Opus, pero en v1.4.0 volvió a sonnet por coste.)
Opus 4.8 tiene tres sesgos de comportamiento documentados que afectan justo a estos agentes:

1. **Sub-utiliza herramientas, subagentes y memoria** por defecto (no "echa mano" de una
   capacidad cara salvo que esté seguro de que hace falta).
2. **Narra más y pregunta más** en decisiones menores.
3. **Escribe más cálido y menos hedged** (bueno para el informe).

Las propuestas contrarrestan (1) y (2) donde duele y aprovechan (3).

---

## P1 — Disparadores explícitos de herramientas en los agentes de explotación
**Agentes:** `web-exploit`, `post-exploit` (Opus 4.8) — y por buena praxis `network-exploit` (sonnet).
**Problema:** 4.8 puede no consultar el RAG / lanzar el tool idóneo si "cree" que puede razonarlo.
**Propuesta — añadir al final del system prompt de cada uno:**
```
Antes de explotar un finding, consulta SIEMPRE su respaldo en el blackboard (cve/msf_modules/
exploit_public del RAG). Si el finding trae módulo MSF, delega/usa esa vía en vez de improvisar.
No te fíes solo del razonamiento: verifica con la herramienta antes de afirmar impacto.
```
**Aceptar si:** quieres que la fase de explotación se apoye en el RAG/herramientas con la misma
agresividad que con Fable. **Rechazar si:** prefieres dejar el prompt como está y validar en vivo.

## P2 — Autonomía en decisiones menores (orquestador + explotación)
**Agentes:** Orquestador (`AGENTS.md`) + agentes de explotación.
**Problema:** 4.8 tiende a parar y preguntar en nimiedades (nombre de fichero, qué flag), lo que en
un run agéntico añade fricción. (El gate de scope + la aprobación por acción ya cubren lo grave.)
**Propuesta — añadir:**
```
Para decisiones menores (nombres, flags equivalentes, orden de pruebas) elige una opción razonable
y anótala; NO preguntes. Reserva las preguntas para cambios de alcance o acciones destructivas
(que además pasan por el gate de scope y la aprobación humana).
```
**Nota:** esto NO afecta a la barrera de seguridad — los comandos ofensivos siguen pidiendo
✅/⛔ por Telegram y el `scope_guard` sigue bloqueando fuera de scope.

## P3 — Control de narración en el canal Telegram
**Dónde:** ya hay una nota de "sé conciso" en el persona del runner (`bot/intel/runner.py`).
**Problema:** 4.8 narra más entre tool-calls; en Telegram eso puede ser ruido.
**Propuesta — endurecer la nota del runner a:**
```
Silencio por defecto entre acciones. Escribe solo cuando: empiezas una fase (1 frase), encuentras
algo, cambias de rumbo, o terminas. No narres acciones rutinarias ("ahora voy a…", "déjame ver…").
```
**Aceptar si:** en el primer test en vivo ves demasiados mensajes intermedios. (Se puede afinar
después de verlo en vivo — no urge.)

## P4 — Revisar el humanizer del informe (reporting ahora Opus 4.8)
**Agente:** `reporting` (Opus 4.8) + `docs/humanizer-checklist.md`.
**Observación:** 4.8 escribe de forma más natural y menos "tell-de-IA" que los modelos previos.
Parte del andamiaje anti-IA del checklist puede sobrecorregir (volverlo seco).
**Propuesta:** NO cambiar nada aún; en el primer informe real, comparar contra el
`humanizer-checklist` y recortar las reglas que ahora sobran. Es un ajuste a hacer **con un informe
delante**, no a ciegas.

---

## Cómo aplicar (si aceptas)
Edita el cuerpo (debajo del frontmatter) del `.md` del agente en `.claude/agents/…` y luego:
```bash
python tools/sync_opencode.py     # propaga a opencode
python tools/build_plugin.py      # reconstruye el plugin
python tools/validate_suite.py    # 0 fallos
```
Las propuestas P1–P2 son las de mayor impacto; P3–P4 se afinan mejor **viendo el bot en vivo**, así
que lo natural es: primer test en vivo → decidir P3/P4 con datos.
