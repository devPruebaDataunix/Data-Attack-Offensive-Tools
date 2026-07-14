# RAG de CONTEXTO per-engagement (context awareness)

El **tercer** RAG, arquitectónicamente distinto de los otros dos. Responde una pregunta que ninguno de
los generales puede: **¿qué se sabe YA de ESTE objetivo?**

| RAG | Pregunta | Alcance | Zona |
| :-- | :-- | :-- | :-- |
| `rag/vulns.db` | ¿QUÉ es vulnerable? (CVE/KEV/EPSS) | general, cross-engagement | repo |
| `rag/knowledge/` | ¿CÓMO explotar/razonar? (técnicas, metodología) | general, cross-engagement | repo (DATO inerte) |
| **`rag/context/`** | **¿qué se sabe ya de ESTE objetivo?** | **per-engagement, efímero** | **EN-ZONA (`engagements/<id>/`, datos de cliente)** |

## Por qué existe
En un engagement largo el conocimiento del objetivo (recon, comportamiento de endpoints, evidencia,
notas) se ACUMULA y no cabe en el contexto del modelo. En vez de releer todo el blackboard, un agente
pregunta por SIGNIFICADO: *"¿qué auth se ha observado en `/orders`?"*, *"¿qué versiones vimos?"*. Eso es
**context awareness**: cruzar el *cómo* general (RAG de conocimiento) con el *qué sabemos aquí* (este RAG).

## Aislamiento (CONSTITUTION §1 — innegociable)
- El store vive en **`engagements/<id>/context.db`** (bajo `engagements/`, **gitignored** → nunca se
  publica; zona E3 de datos de cliente). **NUNCA** en `rag/knowledge/`.
- **Un engagement jamás ve el contexto de otro:** cada uno tiene su propio `context.db`. Las rutas las
  resuelve y **valida** `context_paths.py` (anti path-traversal + la ruta resuelta DEBE quedar bajo
  `engagements/`); testeado en `tests/test_context_rag.py` (sin torch).
- Se indexan `recon/`, `exploit/`, `evidence/`, `notes/`. **NUNCA `loot/`** (credenciales/secretos crudos:
  no se embeben; van referenciados por `secret_ref`). Embeddings **LOCALES** (offline): ningún dato sale de la zona.
- **Efímero:** al cerrar el engagement, `context.db` se va con `engagements/<id>/` (no persiste como el
  conocimiento general). Es contexto de cliente, no aprendizaje transferible (eso es la memoria por-agente).

## Uso
Reusa el store vectorial (`kb_vec`), el embedder local (`embed`) y el troceador (`ingest_corpus.chunk_markdown`)
del RAG de conocimiento; solo el DATO es distinto (per-engagement, en-zona). Como la Capa 2, el poblado con
embeddings usa el venv aislado (`rag/knowledge/.venv`) — es un paso de **Kali** (en Windows los tools degradan
con gracia: compilan, validan el aislamiento y avisan si faltan deps o el store).

```bash
# Poblar/refrescar (tras recon y tras cada fase que deje artefactos):
python rag/context/ingest_context.py -e LAB-2026-009

# Consultar (lo que hacen los agentes antes de disparar):
python rag/context/query_context.py -e LAB-2026-009 --semantic "auth y comportamiento de /orders" --k 6 --json
python rag/context/query_context.py -e LAB-2026-009 -s "versiones de API observadas" --source recon
```

> `context.db` está gitignored (bajo `engagements/`). Idempotente (dedup por hash): refrescar solo embebe
> lo nuevo. El Orquestador lo refresca en el flujo (ver `AGENTS.md`, fase Recon); los agentes de explotación
> lo consultan (`api-exploit` cruza conocimiento + contexto antes de explotar).
