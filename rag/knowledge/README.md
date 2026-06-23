# RAG de conocimiento (técnicas ofensivas)

Complementa al RAG de **CVEs** (`rag/vulns.db` — *"QUÉ es vulnerable"*) con el *"CÓMO explotar/escalar"*:
un catálogo **determinista** de técnicas accionables. La **query es solo stdlib**; los ingesters pueden
usar parsers (PyYAML) porque son un paso **offline**.

## Capa 1 — catálogo estructurado (`kb.db`, SQLite)

| Pieza | Qué hace |
| :-- | :-- |
| `kb.py` | esquema + conexión (tabla `techniques`) |
| `ingest_gtfobins.py` | **GTFOBins** → privesc/exec Linux (SUID/sudo/capabilities, shells, file-read/write) |
| `ingest_lolbas.py` | **LOLBAS** → LOLBins Windows (ejecución, descarga, UAC/AWL bypass, dump, ADS) |
| `ingest_atomics.py` | **Atomic Red Team** → el COMANDO concreto por técnica ATT&CK (Linux/Windows) |
| `ingest_attack.py` | **MITRE ATT&CK** (STIX) → marco táctico (técnicas/sub-técnicas Linux+Windows) |
| `query_kb.py` | **tool que consultan los agentes** (vía Bash), igual que `query_vulns.py` |
| `refresh_kb.py` | clona/descarga las fuentes a `.cache/` y puebla las 4 |

Volumen actual (orientativo): **~4.7k técnicas** = GTFOBins ~2.1k · Atomic ~1.6k · ATT&CK ~0.5k ·
LOLBAS ~0.5k. Plataformas: `linux` / `windows` / `multi` (cross-plataforma; la query la trata como ambas).
Categorías unificadas entre fuentes: `privesc`, `credential-access`, `execution`, `defense-evasion`,
`persistence`, `discovery`, `lateral`, `ingress`, `exfil`, `file-read/write`, … (ATT&CK normaliza
`privilege-escalation→privesc`, `lateral-movement→lateral`, `stealth`/`defense-impairment→defense-evasion`;
la columna `tactic` conserva la táctica MITRE exacta).

### Poblar
```bash
python rag/knowledge/refresh_kb.py
```
GTFOBins, LOLBAS y Atomic se clonan solos; el STIX de ATT&CK se descarga a `.cache/` (si no hay red,
ATT&CK se omite y el resto se puebla igual). Todo es **idempotente** (`INSERT OR IGNORE`).

### Consultar (lo que hacen los agentes)
```bash
python rag/knowledge/query_kb.py --query "env" --category privesc --platform linux   # GTFOBins SUID/sudo
python rag/knowledge/query_kb.py --query "certutil" --platform windows               # LOLBAS
python rag/knowledge/query_kb.py --query "shadow" --source atomic --json             # comando Atomic
python rag/knowledge/query_kb.py --mitre T1003.001                                   # por técnica MITRE
python rag/knowledge/query_kb.py --platform windows --category privesc --source lolbas  # UAC bypass
```

## Capa 2 — semántica (pendiente)
Embeddings sobre prosa (HackTricks, PEASS, writeups, feed **0dayfans**) → recuperación por significado
(`query_kb.py --semantic`). Embeddings: Voyage AI (calidad) o sentence-transformers (offline). Store:
sqlite-vss / FAISS. Ingesta con anti-inyección (todo el contenido externo = DATO).

## Integración con los agentes
El Orquestador inyecta la técnica relevante en la delegación (como hace con `lessons[]`); los agentes
(`post-exploit`, `web-exploit`, `lateral-discovery`, `netexec`…) llaman a `query_kb.py`. El modelo sigue
*stateless*; el conocimiento se actualiza **sin reentrenar** (misma filosofía que el RAG de CVEs).

> Datos generados (`kb.db`, `.cache/`) están gitignored — se reconstruyen con `refresh_kb.py`.
