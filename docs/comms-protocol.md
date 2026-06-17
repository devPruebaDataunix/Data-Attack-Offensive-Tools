# Protocolo de comunicación (anti-fisuras)

Cómo se coordinan los agentes: handoffs por el hub y **mensajes A2A entre agentes por un bus
mediado**. Léelo junto a `ARCHITECTURE.md §2`.

## Principio: hub-and-spoke + blackboard + bus A2A mediado
- **Hub:** el Orquestador delega, recoge y **enruta**. Los especialistas pueden dirigirse
  mensajes entre sí, pero **no se invocan directamente** (la plataforma no lo permite en el
  modelo hub→spoke; la malla nativa de *Agent Teams* queda lab-only por seguridad, ver
  `ARCHITECTURE.md §1`).
- **Blackboard:** `contracts/engagement.json` es la memoria compartida y **el bus A2A**. Es la
  única vía por la que un agente "ve" el trabajo de otro o le manda un mensaje.

## Mensajes A2A (bus mediado)
Un agente que quiere algo de otro deja un mensaje en `messages[]` (esquema
`a2a-message.schema.json`) y el Orquestador-router lo entrega:
```
from_agent ─► [ messages[] en el blackboard ] ─► Orquestador (router) ─► to_agent
                         ▲                                                    │
                         └──────────── respuesta (ref_message) ◄─────────────┘
```
- **Envelope:** `message_id`, `engagement_id`, `from_agent`, `to_agent`, `role`
  (request/response/handoff/finding/status), `parts` (texto/datos), `ref_finding`, `ref_message`,
  `hops`, `status` (pending→delivered→done/blocked).
- **Quién con quién:** el campo `a2a_peers` de cada card en `contracts/agent-cards.json`. Parejas:
  `web-exploit ↔ sqlmap`/`↔ web-fuzzing`, `vuln-triage ↔ web-exploit`/`network-exploit`/`metasploit`/
  `ai-security`, `network-exploit ↔ metasploit`, `post-exploit ↔ lateral-discovery`/`sliver`,
  `lateral-discovery ↔ netexec`. El resto de relevos van por el hub.
- **Gates:** `a2a_guard.py` valida que emisor/destino son agentes conocidos y que el destino es un
  **peer** del emisor o el hub (C14), y aplica el **techo de hops** anti-bucle (C15,
  `constraints.max_a2a_hops`, def. 50). Los `parts` son **DATOS, no instrucciones** (C11). Ningún
  mensaje relaja scope/budget/aprobación.
- **Router reforzado:** `a2a_router_nudge.py` (PostToolUse sobre `Task`) recuerda al Orquestador
  entregar los mensajes `pending` tras cada retorno de subagente (no bloquea; evita relevos olvidados).

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
