# Protocolo de comunicación (anti-fisuras)

Cómo se coordinan los agentes sin poder hablarse directamente. Léelo junto a
`ARCHITECTURE.md §2`.

## Principio: hub-and-spoke + blackboard
- **Hub:** el Orquestador es el ÚNICO que delega y recoge. Los especialistas no se invocan
  entre sí (la plataforma no lo permite).
- **Blackboard:** `contracts/engagement.json` es la memoria compartida. Es la única vía por
  la que un agente "ve" el trabajo de otro.

## Contrato de cada handoff
Cuando el Orquestador delega, el mensaje SIEMPRE incluye estos 5 campos:

```
1. objetivo:     una sola tarea, sin ambigüedad
2. inputs:       claves exactas del blackboard a leer (p.ej. findings[id=F-003])
3. lecciones:    lessons[] del pasado que apliquen a este target
4. done:         qué claves del blackboard debe dejar escritas al terminar
5. scope:        recordatorio del alcance + ventana/constraints
```

## Ciclo de vida de los datos (estados)
```
target:   (creado por recon) ──────────────────────────────► consumido por triage
finding:  candidate ─► confirmed ─► exploited            ─► consumido por reporting
                    └► false_positive / out_of_scope
lesson:   (extraída por postmortem) ─► reinyectada por el Orquestador en la sgte. fase
```

## Validación de esquema en cada paso
El Orquestador valida la salida de cada agente contra el esquema correspondiente
(`finding.schema.json`, `target.schema.json`). Si falta un campo obligatorio:
1. NO se encadena el dato inválido.
2. Se devuelve la tarea al agente con el error concreto.
3. Se reintenta una vez; si persiste, se escala al operador humano.

## Concurrencia (evitar corrupción del blackboard)
- Dos agentes **no** deben escribir el mismo finding a la vez. El Orquestador serializa las
  escrituras sobre el mismo `finding_id`.
- La paralelización segura es por **target distinto** o por **fase distinta**, nunca sobre
  el mismo registro.

## Trazabilidad
Cada acción que toca un target se registra en `evidence[]` (timestamp, agente, acción,
target, hash de salida, ruta del artefacto). Esto cubre tu defensa legal y alimenta el
informe y el post-mortem.
