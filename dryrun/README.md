# Dry run — prueba de la maquinaria de extremo a extremo (sin atacar)

`run_dryrun.py` ejecuta el engagement completo **sin tráfico ofensivo real**: el recon y la
explotación están **simulados** (etiquetados `[SIMULADO]`); el **gate de scope**, el
**triage con el RAG**, el **blackboard** y su **validación de esquema** son **reales**.

Sirve para verificar que toda la fontanería encaja antes de hacerlo de verdad en una VM con
un target autorizado.

## Cómo ejecutarlo
```bash
# 1. Asegúrate de tener el store del RAG poblado:
python rag/refresh.py --epss-all
# 2. Define un scope de laboratorio en contracts/scope.json (hay un ejemplo de lab).
# 3. Lanza el dry run desde la raíz del proyecto:
python dryrun/run_dryrun.py
```

## Qué demuestra (fase a fase)
1. **Recon** `[SIMULADO]` → escribe `targets[]` (host de lab con Apache 2.4.49 + Confluence 7.13).
2. **Gate de scope** `[REAL]` → permite lo de lab, **bloquea** lo de fuera (acme.example, 8.8.8.8).
3. **Triage** `[REAL]` → `vuln-triage` consulta el RAG y crea `findings[]` con KEV/exploit/CVSS/EPSS.
4. **Explotación** `[SIMULADO]` → marca findings como `exploited` con evidencia etiquetada.
5. **Blackboard** → escribe `contracts/engagement.json` y valida contra el esquema.
6. **Reporting** → el agente `reporting` produce `report/INFORME-LAB-2026-009.md` desde el blackboard.

## Salida de ejemplo
- `report/INFORME-LAB-2026-009.md` — informe generado en el dry run.

## Para el run REAL
Abre Claude Code con la raíz en `cyberseg-agents/`, apunta a un laboratorio que controles
(DVWA, Metasploitable, una VM vulnerable) o a un engagement autorizado, con las herramientas
instaladas en la VM de E2 y aprobación humana en los pasos que tocan el target.
