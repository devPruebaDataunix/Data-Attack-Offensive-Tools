# Adapters de informe por plataforma (bug bounty)

Cuando el engagement es un programa de **bug bounty** (`scope.json → program.platform`), el agente
`reporting` puede emitir, ADEMÁS del informe estándar (`templates/report-template.md`), una
**versión por-hallazgo con el formato de envío de la plataforma**. No reimplementan el informe:
reusan los mismos `findings[]` del blackboard y **aplican primero el gate de proof-state (mejora F)**
— un `speculative` no se envía; un `roe-capped` se envía con su salvedad — y el filtro de política de
programa (`rag/triage/query_triage.py`, ADVISORY).

Plantillas disponibles (elige por `program.platform`):
- `hackerone.md` — HackerOne
- `bugcrowd.md` — Bugcrowd (mapeo a la VRT / P1–P5)
- `intigriti.md` — Intigriti (CVSS contextual)
- `yeswehack.md` — YesWeHack

**Regla:** la política OFICIAL del programa PREVALECE sobre estas plantillas y sobre el RAG de
política. Estas plantillas ORIENTAN el formato; el analista humano revisa antes de enviar. Nunca se
envía material sensible en claro (secretos/credenciales redactados, `[REDACTED:identity=<id>]`).
