# Envío Intigriti — {ID}. {Título específico}

**Título:** `{Clase} en {activo} → {impacto de negocio}`

| Campo | Valor |
| :--- | :--- |
| **Categoría** | {taxonomía Intigriti / OWASP} |
| **Severidad (CVSS contextual)** | {Exceptional/Critical/High/Medium/Low} · {score} `{vector}` |
| **CWE** | {CWE-xx} |
| **Endpoint/Asset** | {activo en scope} |
| **Verificación (proof-state F)** | {Explotado / Corroborado / **Limitado por ROE**} · Confianza: {alta/media/baja} |

## Description
{Debilidad, clara.}

## Business impact
{Intigriti prioriza el impacto en CONTEXTO — explícalo concreto para este activo/negocio.}

## Steps to reproduce
1. {paso}
2. {paso}

## Proof of Concept
```
{PoC — secretos redactados}
```
{`roe-capped`: no explotado por ROE; fuente que lo respalda.}

## Recommendation
{Remediación verificable.}

> Intigriti puntúa con **CVSS contextual** (impacto de negocio sobre el base). Comprueba la política
> do-not-report (`query_triage.py --class <clase> --platform intigriti`). La política del programa
> PREVALECE. Revisión humana antes de enviar.
