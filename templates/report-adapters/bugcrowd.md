# Envío Bugcrowd — {ID}. {Título específico}

**Título:** `{Clase VRT} en {activo} → {impacto}`

| Campo | Valor |
| :--- | :--- |
| **VRT (categoría)** | {p.ej. Broken Access Control > IDOR} |
| **Priority (P1–P5)** | {P1 crítico … P5 informativo} — derivado de la VRT + contexto |
| **CWE** | {CWE-xx} |
| **CVSS 3.1** | {score} `{vector}` (referencia; la VRT manda la priority) |
| **Asset** | {activo en scope} |
| **Verificación (proof-state F)** | {Explotado / Corroborado / **Limitado por ROE**} · Confianza: {alta/media/baja} |

## Description
{Debilidad + impacto de negocio.}

## Steps to Reproduce
1. {paso}
2. {paso}

## Proof of Concept
```
{PoC — secretos redactados}
```
{`roe-capped`: no explotado por ROE; fuente que lo respalda.}

## Impact & Remediation
{Impacto concreto · remediación verificable.}

> Mapea la clase a la **VRT** (`https://bugcrowd.com/vulnerability-rating-taxonomy`) para la priority.
> Comprueba la política do-not-report (`query_triage.py --class <clase> --platform bugcrowd`). La VRT y
> la política del programa PREVALECEN. Revisión humana antes de enviar.
