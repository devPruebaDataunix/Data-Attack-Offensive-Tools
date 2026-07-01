# Arquitectura — Cyberseg Agents

## 1. Auditoría crítica del diseño original (los 11 agentes de entonces; hoy 21)

Antes de construir se auditó si los 11 agentes podían "realizar su función y comunicarse
entre ellos sin fisuras". Conclusión: la **taxonomía era correcta**, pero la **plomería
no**. Tres correcciones obligatorias:

### Fallo 1 — Comunicación entre agentes: bus A2A mediado, no malla directa
Los subagentes nativos que invoca el Orquestador (tool `Task`, hub→spoke) corren **aislados**,
cada uno en su ventana de contexto, y **no pueden invocarse entre sí** (sin anidamiento): solo
devuelven un resultado al que los llamó. Desde 2026 Claude Code SÍ ofrece **malla peer real**
(*Agent Teams*: buzones peer-to-peer entre sesiones), pero para una herramienta ofensiva la
descartamos **a propósito en el camino de cliente**, por tres razones de seguridad:
- **Atribución (C10):** la identidad del *teammate* en los hooks de **Agent Teams** se descartó
  ([claude-code#24505](https://github.com/anthropics/claude-code/issues/24505), cerrado como *not
  planned*) → en la malla nativa se rompe la trazabilidad por agente en `evidence[]`, que es
  requisito legal. (Es distinto de los **subagentes** hub→spoke, cuyos hooks sí exponen
  `agent_id`/`agent_type` — ese es el modelo que usamos.)
- **Aprobación humana (C2):** varios teammates en paralelo contra un único canal de aprobación
  (Telegram/TUI) vuelven el gate HITL ingobernable.
- **Madurez:** Agent Teams es experimental; el bot orquesta vía Agent SDK (hub→spoke), no por la
  CLI donde vive el buzón.

Por eso el A2A es **mediado**, sobre dos mecanismos:
1. **Hub-and-spoke + router:** el Orquestador (sesión principal) delega, recoge y **enruta** el
   bus A2A.
2. **Blackboard como bus:** un estado compartido en disco con **esquema definido**
   (`contracts/*.schema.json`). Los agentes se dirigen mensajes en `messages[]`
   (`a2a-message.schema.json`) y leen/escriben sus *inputs*/*outputs* allí; sin contrato de datos
   los handoffs se corrompen. El bus va gateado (`a2a_guard.py`: C14 emisor/destino conocidos +
   C15 techo de hops) y auditado. La malla nativa queda **lab-only, apagada por flag**, hasta que
   se cierre #24505.

### Fallo 2 — El Orquestador no puede ser un subagente
Como los subagentes no pueden lanzar otros subagentes, el Orquestador **es el agente
principal** (la sesión main), descrito en `AGENTS.md`. No es uno de los 21 de la carpeta
`agents/`.

### Fallo 3 — El Scope Guard como agente es saltable
Un agente puede ser ignorado o simplemente no invocado. El control de alcance es un
requisito **legal**, así que se implementa como **hook determinista `PreToolUse`**
(`.claude/hooks/scope_guard.py`) que inspecciona cada comando Bash y lo **bloquea** si
apunta a un host/dominio/CIDR fuera de `contracts/scope.json`. Esto ocurre *antes* de
ejecutar, sin depender del criterio de ningún LLM.

### Otras correcciones aplicadas
- **Solapamiento web/red:** frontera explícita — `web-exploit` cubre capa 7 HTTP(S);
  `network-exploit` cubre servicios no-HTTP y exploits de infraestructura.
- **Discovery duplicado:** `active-recon` hace descubrimiento *externo*;
  `lateral-discovery` hace descubrimiento *interno* post-compromiso.
- **Mínimo privilegio:** cada agente declara solo las tools que necesita; los de
  explotación no tienen escritura en la zona de reporting.
- **Criterios de "done" e I/O explícitos:** cada agente declara qué lee y qué escribe en
  el blackboard, o el Orquestador no puede encadenarlos.

## 2. Modelo de comunicación (hub-and-spoke + blackboard + bus A2A mediado)

```
                         ┌──────────────────────────┐
                         │      ORQUESTADOR          │
                         │   (sesión principal)      │
                         │  lee scope.json + plan    │
                         └─────────────┬─────────────┘
              delega tarea + contexto  │  recoge resultado
        ┌───────────────┬──────────────┼──────────────┬───────────────┐
        ▼               ▼              ▼               ▼               ▼
   osint-recon    active-recon    vuln-triage     web-exploit     ...etc
        │               │              │               │
        └───────────────┴──────┬───────┴───────────────┘
                               ▼
                  contracts/engagement.json   ← BLACKBOARD (estado compartido + bus A2A)
                  (targets[], findings[], messages[], lessons[], evidence[])
                               ▲
                               │ lee lecciones del pasado
                     knowledge-postmortem  (memory: project)
```

Regla de oro: **ningún agente asume nada que no esté en el blackboard.** Si necesita un
dato, lo lee de `contracts/engagement.json`; si produce un dato, lo escribe allí con el
esquema correcto. El Orquestador valida el esquema en cada handoff. Para hablar con otro
agente, un especialista **no lo invoca**: deja un mensaje en `messages[]`
(`a2a-message.schema.json`) y el Orquestador-router lo entrega al destino (ver `AGENTS.md` →
"Bus A2A"). Los mensajes A2A son **datos auditados**, nunca instrucciones (C11/C14).

## 3. Las tres zonas de aislamiento

(Recordatorio de la decisión previa: ni todo junto ni un entorno por agente.)

| Zona | Agentes | Red | Datos | Riesgo |
| :--- | :--- | :--- | :--- | :--- |
| **E1 Recon** | osint-recon, active-recon | internet amplia / ruta al target | sin datos de cliente | bajo |
| **E2 Explotación** | vuln-triage, web-exploit, network-exploit, post-exploit, lateral-discovery, c2-exfil | **solo** VLAN del engagement, kill-switch, snapshots | acceso al target | alto |
| **E3 Cierre** | reporting, knowledge-postmortem | sin egress de datos crudos, modelo ZDR | datos de cliente | medio |

**Aislamiento por cliente dentro de E2:** una VM/namespace por engagement, destruida al
cerrar. Nunca compartas E2 entre dos clientes simultáneos.

El Orquestador es el plano de control; no ejecuta tooling ofensivo por sí mismo.

## 4. Mapa ATT&CK → agentes (E2)

| Agente | Tácticas MITRE ATT&CK cubiertas |
| :--- | :--- |
| osint-recon | Reconnaissance (TA0043), Resource Development (TA0042) |
| active-recon | Reconnaissance (activa), Discovery externa |
| vuln-triage | (puente: correlación CVE/KEV → priorización) |
| web-exploit | Initial Access (TA0001), Execution (TA0002) — vector web |
| network-exploit | Initial Access, Execution — vector red/infra |
| metasploit | Initial Access, Execution, PrivEsc, Lateral Movement — operador senior de MSF |
| post-exploit | Privilege Escalation (TA0004), Persistence (TA0003), Defense Evasion (TA0005), Credential Access (TA0006) |
| lateral-discovery | Discovery (TA0007), Lateral Movement (TA0008), Collection (TA0009) |
| c2-exfil | Command and Control (TA0011), Exfiltration (TA0010), Impact (TA0040) — simulado |

## 5. Asignación de modelos (coste vs. razonamiento)

Routing por tier para no quemar cupo de Pro (sin `CLAUDE_CODE_SUBAGENT_MODEL`): cada agente
fija su propio `model`. Distribución real: **6 haiku · 11 sonnet · 4 opus-4-8** (sin fable).

| Tier | Agentes | Motivo |
| :--- | :--- | :--- |
| `claude-haiku-4-5` | osint-recon, recon-suite, active-recon, web-fuzzing, nuclei, knowledge-postmortem | recon/escaneo/parseo mecánico: mucho dato, poco razonamiento (sin `effort`) |
| `claude-sonnet-4-6` | vuln-triage, sqlmap, metasploit, netexec, ad-enum, kerberos, adcs, sliver, lateral-discovery, c2-exfil, network-exploit | tool-driving con juicio / el RAG hace el trabajo pesado |
| `claude-opus-4-8` | web-exploit, post-exploit, ai-security, reporting | razonamiento ofensivo profundo + informe |

> El inventario completo y siempre al día (modelo por agente) vive en `ARCHITECTURE_MAP.md`
> (auto-generado). Esta tabla es el resumen por tier. El Orquestador (sesión principal) usa opus-4-8.
