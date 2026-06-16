# Arquitectura — Cyberseg Agents

## 1. Auditoría crítica del diseño original (los 11 agentes de entonces; hoy 18)

Antes de construir se auditó si los 11 agentes podían "realizar su función y comunicarse
entre ellos sin fisuras". Conclusión: la **taxonomía era correcta**, pero la **plomería
no**. Tres correcciones obligatorias:

### Fallo 1 — La comunicación "entre agentes" no existe como peer-to-peer
En Claude Code y opencode los subagentes:
- corren **aislados**, cada uno en su propia ventana de contexto;
- **no pueden hablar entre sí** directamente;
- **no pueden invocar a otros subagentes** (sin anidamiento).

Solo devuelven un **resultado** al que los invocó. Por tanto, "comunicación sin fisuras"
se implementa con dos mecanismos, no con mensajería directa:
1. **Hub-and-spoke:** el Orquestador (sesión principal) es el único que delega tareas y
   recoge resultados.
2. **Blackboard:** un estado compartido en disco con **esquema definido**
   (`contracts/*.schema.json`). Cada agente lee sus *inputs* y escribe sus *outputs* en
   ese estado. Sin contrato de datos, los handoffs se corrompen.

### Fallo 2 — El Orquestador no puede ser un subagente
Como los subagentes no pueden lanzar otros subagentes, el Orquestador **es el agente
principal** (la sesión main), descrito en `AGENTS.md`. No es uno de los 18 de la carpeta
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

## 2. Modelo de comunicación (hub-and-spoke + blackboard)

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
                  contracts/engagement.json   ← BLACKBOARD (estado compartido)
                  (targets[], findings[], lessons[], evidence[])
                               ▲
                               │ lee lecciones del pasado
                     knowledge-postmortem  (memory: project)
```

Regla de oro: **ningún agente asume nada que no esté en el blackboard.** Si necesita un
dato, lo lee de `contracts/engagement.json`; si produce un dato, lo escribe allí con el
esquema correcto. El Orquestador valida el esquema en cada handoff.

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
fija su propio `model`. Distribución real: **6 haiku · 8 sonnet · 4 opus-4-8** (sin fable).

| Tier | Agentes | Motivo |
| :--- | :--- | :--- |
| `claude-haiku-4-5` | osint-recon, recon-suite, active-recon, web-fuzzing, nuclei, knowledge-postmortem | recon/escaneo/parseo mecánico: mucho dato, poco razonamiento (sin `effort`) |
| `claude-sonnet-4-6` | vuln-triage, sqlmap, metasploit, netexec, sliver, lateral-discovery, c2-exfil, network-exploit | tool-driving con juicio / el RAG hace el trabajo pesado |
| `claude-opus-4-8` | web-exploit, post-exploit, ai-security, reporting | razonamiento ofensivo profundo + informe |

> El inventario completo y siempre al día (modelo por agente) vive en `ARCHITECTURE_MAP.md`
> (auto-generado). Esta tabla es el resumen por tier. El Orquestador (sesión principal) usa opus-4-8.
