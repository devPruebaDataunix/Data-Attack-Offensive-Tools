# Guía de redacción de informes de pentest (cómo lo hacen los profesionales)

Síntesis de cómo redacta un informe un pentester experimentado, destilada de estándares y
recursos reales (ver Fuentes). El agente `reporting` sigue esta guía.

## Principio rector
Un informe tiene **dos lectores** y un buen informe sirve a ambos sin mezclarlos:
- **Dirección / negocio** (no técnico): quiere riesgo, impacto en el negocio y qué hacer.
- **Ingeniería** (técnico): quiere detalle reproducible y remediación concreta.

Regla de oro de redacción: **traduce el hallazgo a impacto de negocio.**
> ❌ "Se identificó una inyección SQL."
> ✅ "Un atacante podría acceder a la base de datos de clientes y exponer los datos
>    personales de ~50.000 usuarios."

## Estructura del informe (orden estándar)

1. **Resumen ejecutivo** (1-2 páginas, lenguaje llano, sin jerga)
   - Una frase de alcance: qué se probó, cuándo y con qué enfoque.
   - Postura de riesgo global en una frase.
   - Recuento por severidad (crítico/alto/medio/bajo) + estado de resolución.
   - Los 3-5 hallazgos de mayor impacto, en lenguaje de negocio.
   - Recomendaciones estratégicas (conectan hallazgos con próximos pasos).
2. **Alcance y reglas de enganche (ROE)**
   - Activos en scope, ventana de pruebas, autorización (referencia de contrato), límites
     y exclusiones. Qué NO se probó y por qué.
3. **Metodología**
   - Marcos seguidos: **PTES, OWASP WSTG, NIST SP 800-115, MITRE ATT&CK**.
   - Fases (recon → enumeración → explotación → post-explotación) y herramientas.
4. **Hallazgos** (técnico, **priorizados por severidad y luego explotabilidad**)
   - Un bloque por hallazgo con el formato de abajo.
5. **Hoja de ruta de remediación** (priorizada)
   - Quick wins primero (p.ej. "parchear X"), luego mejoras estratégicas (SDLC, formación).
   - En el orden en que deben abordarse.
6. **Anexos**
   - Evidencia extendida, salida de herramientas, referencias CVE/KEV, glosario.

## Formato de cada hallazgo (lo que un buen finding contiene)

| Campo | Contenido | De dónde sale |
| :--- | :--- | :--- |
| **ID + título** | Específico y claro (no genérico) | — |
| **Severidad** | Crítico / Alto / Medio / Bajo / Info | RAG (tier KEV>exploit>EPSS>CVSS) |
| **CVSS 3.1** | Score base **+ vector string** (defendible) | `finding.cvss` + `cvss_vector` (CVE 5.0) |
| **CWE / OWASP / ATT&CK** | Clasificación | `finding.cwe/owasp/attack_technique` |
| **Cadena de ataque** | Eslabón siguiente si encadena | `finding.next_step` (suggested_agent/technique) |
| **Activos afectados** | Hosts/URLs | `finding.target_id` → `targets[]` |
| **Descripción** | Qué es la debilidad, en claro | redacción |
| **Impacto de negocio** | Qué podría lograr un atacante, concreto | redacción (traducir, no jerga) |
| **Pasos de reproducción** | Numerados, exactos, repetibles | `finding.reproduction` + `evidence[]` |
| **Evidencia** | Request/response, PoC, captura (placeholder) | `evidence[]` (redactar secretos) |
| **Remediación** | Acción concreta y verificable, priorizada | `finding.remediation` |
| **Referencias** | CVE/KEV/EPSS/advisory | `finding.source_refs` |
| **Estado** | Confirmado / Explotado | `finding.status` |

> Bandas CVSS 3.1: Crítico 9.0-10.0 · Alto 7.0-8.9 · Medio 4.0-6.9 · Bajo 0.1-3.9.
> **Pero la severidad final no es solo CVSS:** un crítico en un sistema interno aislado
> puede ser menos urgente que un alto expuesto a internet. Prioriza con el contexto del
> RAG (KEV / exploit público / EPSS / exposición), no ordenando por número.

## Reglas de calidad
- Cada afirmación, respaldada por evidencia del blackboard. Sin evidencia, no es un hallazgo.
- Nada inventado: si no está confirmado, no va (o va claramente como "informativo/no
  confirmado").
- Remediación siempre **accionable y verificable**, en orden de prioridad.
- Secretos/credenciales **redactados**, nunca en claro.
- El informe lo **revisa un humano** antes de entregarse. Indícalo.

## Redacción que NO parezca generada por IA
Ver `humanizer-checklist.md`. Resumen: lenguaje específico y anclado en la evidencia, frases
de longitud variada, voz activa, cero relleno y cero vocabulario-IA. Un informe que parece
de plantilla automática pierde credibilidad ante el cliente.

## Fuentes
- OWASP Penetration Test Reporting Standard (OPTRS): https://owasp.org/www-project-penetration-test-reporting-standard/
- OWASP Web Security Testing Guide (WSTG): https://owasp.org/www-project-web-security-testing-guide/
- NIST SP 800-115 (Technical Guide to Security Testing): https://csrc.nist.gov/pubs/sp/800/115/final
- PTES (Penetration Testing Execution Standard): http://www.pentest-standard.org/
- Plantilla OSCP (noraj): https://github.com/noraj/OSCP-Exam-Report-Template-Markdown
- Plantillas DOCX/PDF (OWASP/PTES/NIST): https://github.com/MSaiRam10/pentest-report-templates
- FIRST CVSS v3.1 spec: https://www.first.org/cvss/v3-1/specification-document
