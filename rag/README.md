# RAG de Vulnerabilidades — KEV + EPSS (alimenta a `vuln-triage`)

Pipeline que mantiene al agente `vuln-triage` **al día con las vulnerabilidades que de
verdad se están explotando**. Sin dependencias externas (solo Python stdlib + SQLite).

## Por qué este diseño (criterio experto 2026)

No es un "RAG ingenuo" de embeddings sobre descripciones de CVE (impreciso para matching
producto/versión). Es **retrieval híbrido con priorización basada en riesgo**, el estándar
actual de vulnerability management:

| Señal | Qué aporta | Peso |
| :--- | :--- | :--- |
| **CISA KEV** | Explotación **confirmada** en el mundo real | 🔴 Máxima |
| **Exploit público** (ExploitDB / eip) | Existe PoC/exploit publicado | 🔴 Muy alta |
| **VulnCheck KEV** | KEV ampliada (más que la de CISA) | 🟠 Alta |
| **EPSS** (FIRST.org) | Probabilidad (0-1) de explotación a 30 días | 🟠 Alta |
| **CVSS** (CVE 5.0 / CNA, **no NVD**) | Severidad si se explota | 🟡 Media |
| **SSVC** (CISA Vulnrichment) | Decisión exploitation/automatable/impact | 🟡 Contexto |
| Relevancia textual | ¿pertenece al producto consultado? | Gate previo |

> Regla de oro (FIRST): *si hay evidencia de explotación, eso supera a cualquier score
> predictivo.* Por eso el orden es **KEV > exploit público > EPSS > CVSS**.

El ranking es **dos etapas**: (1) relevancia — ¿este CVE es de este producto? (gate sobre
vendor/product/name); (2) prioridad de explotación — KEV > exploit público > EPSS > CVSS.

### Por qué CVSS desde CVE 5.0 y NO desde el NVD
El NVD está degradado: backlog masivo desde 2024, y desde el **15-abr-2026** NIST solo
enriquece CVEs de alto riesgo (KEV/federal/crítico); su severidad es errónea ~88% de las
veces (Inspector General). Por eso tomamos el CVSS del **registro CVE 5.0** (lo publica el
propio CNA) y el SSVC/KEV del contenedor **CISA-ADP (Vulnrichment)**. Fuente pública, fiable
y sin depender del NVD.

## Uso

```bash
# 1. Poblar / refrescar el store (KEV + EPSS). Hazlo la primera vez y luego a diario.
python rag/refresh.py            # rápido: solo enriquece EPSS nuevo
python rag/refresh.py --epss-all # completo: re-enriquece EPSS de todo (cambia a diario)

# 2. Consultar (lo que hace vuln-triage por dentro)
python rag/query_vulns.py --query "Fortinet FortiOS SSL VPN"
python rag/query_vulns.py --query "Apache Log4j" --json
python rag/query_vulns.py --query "Microsoft Exchange" --kev-only --min-epss 0.5 --limit 10
```

Salida `--json`: lista `results[]` lista para mapear a `finding.schema.json` (cve, title,
severity, in_kev, epss, cwe, source_refs...), más metadatos de frescura del store.

## Componentes

| Fichero | Función |
| :--- | :--- |
| `db.py` | Esquema SQLite + migración + helpers (store `vulns.db`) |
| `ingest_kev.py` | Descarga el catálogo CISA KEV y lo upserta |
| `ingest_recent.py` | **Frescura**: CVE recién publicados (CVEDetector + OpenCVE) que aún no están en KEV |
| `enrich_cve5.py` | CVSS + SSVC desde CVE 5.0 (CNA + CISA-ADP), **no NVD** |
| `enrich_exploits.py` | Exploit público: ExploitDB (offline) + eip-mcp (opcional) |
| `enrich_epss.py` | Añade scores EPSS (lotes de 50, con reintentos) |
| `query_vulns.py` | Retrieval híbrido rankeado (lo llama el agente) |
| `refresh.py` | Orquesta KEV + recientes + CVE5 + exploits + MSF + Nuclei + EPSS para cron/Task Scheduler |

### Frescura: CVE recién publicados (`ingest_recent.py`)
KEV va con meses de retraso respecto a la publicación. `ingest_recent.py` añade los CVE **recientes** que
aún no tenemos, desde feeds de frescura, y los marca con `source_feed`/`published_date` (in_kev=0). Luego
los enrichers les ponen CVSS/EPSS/exploit en el mismo refresco. Corre dentro de `refresh.py` (constante).
- **CVEDetector** (canal Telegram, preview web público `t.me/s/CVEDetector`): sin auth. Su lado prosa
  también va al RAG semántico (Capa 2, `rag/knowledge/ingest_feeds.py`).
- **OpenCVE** (API v2 de `app.opencve.io`): **requiere credenciales** → `OPENCVE_USERNAME`/`OPENCVE_PASSWORD`
  (nunca en el repo). Sin ellas se omite con aviso.
- **Anti-inyección**: todo el contenido remoto es DATO inerte; nunca se ejecuta.

```bash
python rag/ingest_recent.py                    # CVEDetector (+ OpenCVE si hay credenciales)
OPENCVE_USERNAME=u OPENCVE_PASSWORD=p python rag/ingest_recent.py --opencve-pages 3
```

`vulns.db` se genera; **no** se versiona ni se incluye en el paquete (caduca). Ejecuta
`refresh.py` para crearlo.

## Programación (mantenerlo al día solo)

**Windows (Task Scheduler):**
```
schtasks /Create /SC DAILY /ST 06:00 /TN "cyberseg-rag-refresh" ^
  /TR "python C:\ruta\cyberseg-agents\rag\refresh.py --epss-all"
```
**Linux/macOS (cron):** `0 6 * * * cd /ruta/cyberseg-agents && python rag/refresh.py --epss-all`

## Capa híbrida de enriquecimiento (eip-mcp self-hosted) — opcional

El núcleo (KEV + CVSS de CVE5 + ExploitDB + EPSS) funciona **sin claves y offline** una vez
sincronizado, ideal para la zona E2 aislada. La capa híbrida añade inteligencia de exploits
más rica (VulnCheck KEV, InTheWild, Metasploit/Nuclei, madurez del exploit) vía
**eip-mcp** (Exploit Intelligence Platform, MIT, self-hostable, sin API key).

**Por qué híbrido y no MCP-en-vivo:** (1) E2 suele estar aislada → un MCP externo no es
alcanzable; el store local sí. (2) Opsec/NDA: consultar un servicio externo sobre el
producto del target **filtra a un tercero qué cliente auditas**. (3) En 2026 se publicaron
**+40 CVEs contra implementaciones de MCP** (RCE, command injection, path traversal); la
NSA sacó guía. Por eso el MCP se usa **self-hosted, en sandbox y solo en el lado con red**,
como motor que rellena el store local — nunca como dependencia en caliente de E2.

Activación:
```bash
# 1. Instala y arranca eip-mcp self-hosted (en el plano de control / E1, NO en E2):
pipx install eip-mcp            # github.com/exploitintel/eip-mcp (MIT)
# 2. Apunta el enriquecedor a tu instancia y refresca:
EIP_API_URL=http://127.0.0.1:8000  python rag/enrich_exploits.py
# 3. (Opcional) Para exponerlo a vuln-triage como tool en línea: renombra
#    .mcp.json.example -> .mcp.json   (SOLO en el workspace del plano de control)
```

### Seguridad del MCP (obligatorio si lo activas)
Somos una empresa de seguridad: trata el MCP como código no confiable.
- **Pin de versión** y revisión del binario; no `latest` ciego.
- **Sandbox** (contenedor/usuario sin privilegios) y **sin exposición a red pública**
  (bind a `127.0.0.1`).
- **Nunca** cargues `.mcp.json` con eip en agentes de E2 ni en redes de cliente.
- Si self-hospedas también la EIP API, mejor: cero dependencia externa.

### Sobre el NVD (por qué ya no lo usamos para CVSS)
NVD API 2.0 sigue existiendo (5 req/30s sin clave) pero su enriquecimiento está limitado
desde abr-2026 y su severidad es poco fiable. Usamos CVE 5.0 + CISA-ADP en su lugar. Si
aun así quieres NVD como respaldo, su clave gratuita está en
https://nvd.nist.gov/developers/request-an-api-key (guárdala en `NVD_API_KEY`, nunca en el repo).

## Ruta de producción: Supabase + n8n (tu stack)

El SQLite local es ideal para un operador. Para **equipo** y para integrarlo con tu
infraestructura existente, replica el store en Supabase (Postgres + pgvector si añades
búsqueda semántica). Patrón equivalente a tu Market Bot:

1. **Tabla `vulns`** en Supabase con las mismas columnas que `db.py` (PK `cve_id`).
2. **Workflow n8n `WF_KEV_Ingest`** (Schedule diario 06:00):
   `HTTP Request` GET al feed KEV → `Code`/`Set` para normalizar →
   `Supabase` upsert (`on_conflict=cve_id`, `Prefer: resolution=merge-duplicates`).
3. **Workflow n8n `WF_EPSS_Enrich`**: por lotes de 50 CVE, GET a
   `https://api.first.org/data/v1/epss?cve=...` → `Supabase` PATCH `epss`/`epss_percentile`.
4. **Retrieval para los agentes**: función SQL `match_vulns(query text)` o una RPC que
   replique el ranking de `query_vulns.py` (relevancia × 10000 + KEV/EPSS/CVSS), expuesta
   vía MCP de Supabase o un endpoint que el agente llame.

> Si añades búsqueda semántica: columna `embedding vector(1536)` (text-embedding-3-small
> vía OpenRouter, como en tu bot), e híbrido = filtro estructurado (producto) + `match`
> por similitud sobre la descripción. Para CVE, el matching estructurado pesa más que el
> semántico: úsalo como complemento, no como sustituto.

## Fuentes
- CISA KEV: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- CVEDetector (Telegram, frescura): https://t.me/s/CVEDetector
- OpenCVE (API v2, frescura, requiere cuenta): https://app.opencve.io/cve/ · https://docs.opencve.io/api/
- EPSS API: https://www.first.org/epss/api
- CVE 5.0 (MITRE CVE Services): https://cveawg.mitre.org/api/cve/{CVE-ID}
- CISA Vulnrichment (SSVC): https://github.com/cisagov/vulnrichment
- ExploitDB: https://gitlab.com/exploit-database/exploitdb
- eip-mcp (Exploit Intelligence Platform): https://github.com/exploitintel/eip-mcp
- VulnCheck NVD++ (alternativa al NVD): https://www.vulncheck.com/nvd2
- OSV.dev: https://osv.dev
- NVD API 2.0 (degradado, solo respaldo): https://nvd.nist.gov/developers/vulnerabilities
