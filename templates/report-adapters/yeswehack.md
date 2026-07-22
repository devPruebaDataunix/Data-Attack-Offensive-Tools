# Envío YesWeHack — {ID}. {Título específico}

**Título:** `{Clase} en {activo} → {impacto}`

| Campo | Valor |
| :--- | :--- |
| **Categoría (CWE)** | {CWE-xx — nombre} |
| **Severidad (CVSS 3.1)** | {Low/Medium/High/Critical} · {score} `{vector}` |
| **Scope / Asset** | {activo EN SCOPE — YWH es estricto con el scope} |
| **Verificación (proof-state F)** | {Explotado / Corroborado / **Limitado por ROE**} · Confianza: {alta/media/baja} |

## Bug description
{Debilidad + impacto.}

## Steps to reproduce
1. {paso}
2. {paso}

## Proof of Concept
```
{PoC — secretos redactados}
```
{`roe-capped`: no explotado por ROE; fuente que lo respalda.}

## Impact / Remediation
{Impacto concreto · remediación verificable.}

> YesWeHack aplica **reglas de scope estrictas**: confirma que el activo está EN SCOPE (un hallazgo
> válido fuera de scope no se recompensa). Comprueba la política do-not-report
> (`query_triage.py --class <clase> --platform yeswehack`). La política del programa PREVALECE.
> Revisión humana antes de enviar.
