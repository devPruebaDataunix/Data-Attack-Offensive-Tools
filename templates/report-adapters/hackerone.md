# Envío HackerOne — {ID}. {Título específico}

**Título del report:** `{Clase concisa} en {activo/endpoint} permite {impacto}`
_(H1 valora títulos accionables: qué + dónde + impacto; sin relleno.)_

| Campo | Valor |
| :--- | :--- |
| **Weakness (CWE)** | {CWE-xx — nombre} |
| **Severity (CVSS 3.1)** | {None/Low/Medium/High/Critical} · {score} `{vector}` |
| **Asset** | {dominio/URL/API en scope} |
| **Verificación (proof-state F)** | {Explotado (PoC) / Corroborado / **Limitado por ROE** (respaldado por fuente, no explotado por alcance)} · Confianza: {alta/media/baja} |

## Summary
{Qué es la debilidad y su impacto de negocio, en 2-3 frases claras.}

## Steps To Reproduce
1. {paso exacto}
2. {paso}
_(Para IDOR/BOLA: el par request/response de AMBAS identidades, tokens redactados `[REDACTED:identity=<id>]`.)_

## Proof of Concept
```
{request/response o comando — secretos redactados}
```
{Si es `roe-capped`: indica que NO se explotó por ROE y en qué fuente (CVE/KEV/exploit público) se sustenta.}

## Impact
{Qué logra un atacante; concreto, sin jerga.}

## Remediation
{Acción verificable.}

> Antes de enviar: verifica que la clase no está en la política do-not-report del programa
> (`rag/triage/query_triage.py --class <clase> --platform hackerone`) salvo que aplique su excepción.
> La política oficial del programa PREVALECE. Revisión humana obligatoria.
