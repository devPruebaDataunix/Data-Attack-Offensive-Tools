# Informe de Test de Intrusión — {CLIENTE}

| | |
| :--- | :--- |
| **Cliente** | {cliente} |
| **Engagement** | {engagement_id} |
| **Tipo** | {pentest web / red / interno / bug bounty} |
| **Ventana de pruebas** | {fecha_inicio} – {fecha_fin} |
| **Autorización** | {referencia de contrato / ROE} |
| **Autor** | {tester} · **Revisado por** | {revisor humano} |
| **Clasificación** | CONFIDENCIAL |

> ⚠️ Borrador asistido. **Requiere revisión humana** antes de la entrega al cliente.

---

## 1. Resumen ejecutivo

{Una frase de alcance: qué se probó, cuándo, con qué enfoque.}

{Postura de riesgo global en una frase.}

**Resumen de hallazgos:**

| Severidad | Nº |
| :--- | :---: |
| Crítico | {n} |
| Alto | {n} |
| Medio | {n} |
| Bajo | {n} |
| Informativo | {n} |

**Hallazgos de mayor impacto (en lenguaje de negocio):**
1. {Hallazgo 1 — qué podría lograr un atacante y qué activo/dato pone en riesgo.}
2. {…}
3. {…}

**Recomendaciones estratégicas:** {2-4 acciones que conectan los hallazgos con próximos pasos.}

## 2. Alcance y reglas de enganche

- **En scope:** {activos}
- **Fuera de scope / límites:** {exclusiones}
- **Qué no se pudo probar y por qué:** {limitaciones}

## 3. Metodología

Marcos seguidos: PTES · OWASP WSTG · NIST SP 800-115 · MITRE ATT&CK.
Fases: reconocimiento → enumeración → explotación → post-explotación → reporte.
{Herramientas y enfoque resumidos.}

## 4. Hallazgos

> Ordenados por severidad y luego por explotabilidad real (KEV / exploit público / EPSS).

### {ID}. {Título específico del hallazgo}

| | |
| :--- | :--- |
| **Severidad** | {Crítico/Alto/Medio/Bajo} |
| **CVSS 3.1** | {score} (`{vector}`) |
| **Clasificación** | {CWE-xx} · {OWASP A0x} · {ATT&CK Txxxx} |
| **Activos afectados** | {hosts/URLs} |
| **Estado** | {Confirmado / Explotado} |
| **Referencias** | {CVE / KEV / advisory} |

**Descripción.** {Qué es la debilidad, en claro.}

**Impacto de negocio.** {Qué podría lograr un atacante, concreto y sin jerga.}

**Pasos de reproducción.**
1. {paso}
2. {paso}

**Evidencia.**
```
{request/response, salida de comando o PoC — secretos redactados}
```
{captura: evidencia/{id}.png}

**Cadena de ataque.** {Si este hallazgo es eslabón de una cadena: el siguiente paso y su técnica (campo `next_step`), p.ej. "→ DCSync (T1003.006) vía netexec". Omitir si no encadena.}

**Remediación.** {Acción concreta y verificable.}

---

{repetir bloque por cada hallazgo}

## 5. Hoja de ruta de remediación

| Prioridad | Acción | Hallazgos | Plazo sugerido |
| :--- | :--- | :--- | :--- |
| 1 (inmediata) | {quick win} | {IDs} | {plazo} |
| 2 | {…} | | |
| 3 (estratégica) | {SDLC / formación / arquitectura} | | |

## 6. Anexos

- A. Evidencia extendida y salida de herramientas.
- B. Referencias CVE/KEV y enlaces.
- C. Glosario para lectores no técnicos.
