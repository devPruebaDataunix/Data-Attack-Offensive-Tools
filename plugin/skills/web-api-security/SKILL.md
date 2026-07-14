---
name: web-api-security
description: Metodología de pentest de APIs (REST/GraphQL) mapeada al OWASP API Security Top 10 (2023) — BOLA, broken auth, BOPLA, consumo de recursos, BFLA, abuso de flujos de negocio, SSRF, misconfiguration, inventario impropio y consumo inseguro de terceros. Úsala cuando el activo en scope exponga una API, rutas /api, swagger/openapi.json, un endpoint GraphQL o el backend de una app móvil. La usan los agentes api-recon (inventario) y api-exploit (explotación).
---

# Seguridad ofensiva de APIs (REST / GraphQL) — OWASP API Top 10 (2023)

Las APIs son hoy el vector #1: el fallo casi nunca es la inyección clásica, sino la **autorización
a nivel de objeto y de función**. Su prueba corroborable exige **múltiples identidades** (testing
diferencial). Esta skill es la metodología; la ejecutan `api-recon` (inventario) y `api-exploit`
(explotación).

## Cuándo usarla
Tras descubrir una API en scope: rutas `/api`, `/v1`, `graphql`, `swagger`/`openapi.json`,
`.well-known/`, cabeceras `Authorization: Bearer`, `Content-Type: application/json`, o el backend
que consume una app móvil. Confirma alcance en `contracts/scope.json` antes de tocar nada.

## Fase 0 — Inventario (api-recon): la spec es el mapa
Sin inventario no hay corroboración. Cosecha la spec publicada (`openapi.json`, `/v3/api-docs`,
`swagger-ui`) o reconstrúyela desde tráfico (patrón `mitmproxy2swagger`/`APIClarity`). Enumera
**todas las versiones** (`/v1` vs `/v2`, `/internal`, staging, backend-móvil → API9). GraphQL:
fingerprint (`graphw00f`), introspección (`__schema`) o reconstrucción si está desactivada
(`clairvoyance`, InQL). Deja endpoints/métodos/parámetros/esquema/tipo-de-auth estructurados en el target.

## Fase 1 — Identidades de prueba (el arnés diferencial)
BOLA/BFLA/BOPLA **solo se corroboran con ≥2 identidades** que el programa autorice. Cárgalas en
`identities[]` del engagement (referenciadas: el token/cookie va a `engagements/<id>/loot/`, nunca en
claro — lo imponen `memory_guard`/`secret_scan`). Patrón mínimo: `userA` y `userB` del mismo rol (para
authz horizontal) y opcionalmente `admin` y `anon` (para vertical). Marca `owns_objects` de cada una.

## Fase 2 — Método OWASP API Top 10 (2023)
- **API1 · BOLA / IDOR** (T1190): con A crea/lee un objeto; **repite la misma request con el token de B**.
  Si B accede al objeto de A → confirmado. Prueba IDs incrementales, UUIDs en body/query, objetos anidados.
  La evidencia es el **par request/response de AMBAS identidades**. Causa de >50% de las brechas de API.
- **API2 · Broken Authentication**: JWT (`alg:none`, confusión RS256→HS256, secreto débil, firma/`exp` no
  verificados, token en URL), OAuth roto, reset de password, credential stuffing controlado. Skill `jwt-oauth`.
- **API3 · BOPLA**: *mass assignment* (inyecta `"role":"admin"`, `"isVerified":true`, `"balance":9999`) +
  *excessive data exposure* (la respuesta trae más campos que la UI: PII, hashes, flags internos).
- **API4 · Unrestricted Resource Consumption**: rate-limit ausente/eludible, paginación sin tope, GraphQL
  (profundidad/anidamiento, **batching/alias**), ReDoS. Demuestra impacto **sin** DoS real.
- **API5 · BFLA**: funciones de mayor privilegio con identidad baja (métodos no enlazados en UI, `/admin`,
  `DELETE`/`PUT`). Diferencial: lo que admin puede y user NO debería.
- **API6 · Unrestricted Access to Sensitive Business Flows**: flujos sensibles (compra, registro, invitación)
  sin anti-automatización → scriptables (acaparar stock, farmear). El finding es la ausencia de defensa del flujo.
- **API7 · SSRF** (T1190): parámetros `url=`/`webhook=`/`image_url=`/`callback=` → metadata/servicios internos
  EN SCOPE. Demuestra pivote con canary, sin exfil real.
- **API8 · Security Misconfiguration**: CORS permisivo (`ACAO:*` con credenciales, reflejo de Origin), errores
  verbosos, métodos de más, headers ausentes, TRACE/OPTIONS, debug endpoints.
- **API9 · Improper Inventory Management**: explota APIs sombra/zombi (versiones viejas sin el parche que sí
  tiene la nueva, staging expuesto) — de lo más rentable en bug bounty.
- **API10 · Unsafe Consumption of APIs**: si la API consume upstream/terceros sin validar, inyecta por esa
  cadena de confianza.
- **GraphQL transversal**: introspección, IDOR por nodo, batching para brute-force/rate-bypass, mutations no
  autorizadas, inyección en resolvers.

## Herramientas (suite del repo + referencia awesome-api-security)
- **Inventario/spec:** `api-recon` (cosecha OpenAPI/Swagger, GraphQL introspection); `recon-suite`
  (httpx/katana/gau); `web-fuzzing` (ffuf/feroxbuster con wordlists de API) — tier **normal**.
- **Fuzzing dirigido por spec (a integrar como tool-agents):** `schemathesis` (property-based desde
  OpenAPI, estándar de facto), `RESTler` (stateful: aprende la secuencia de dependencias), CATS/APIFuzzer.
- **GraphQL:** `graphw00f` (fingerprint), `clairvoyance`/InQL (esquema), GraphQLmap/BatchQL.
- **Inyección:** `sqlmap` sobre parámetros de API — tier **sensitive** (pide aprobación).
- **Plantillas:** `nuclei` (tags `exposure`, `graphql`, `swagger`, tokens filtrados).
- **Captura/replay:** proxy (Burp/mitmproxy) para el par diferencial de BOLA/BFLA.

## Evidencia y alcance
- **Sin fuente no se explota**: un BOLA es finding solo con el par request/response de las DOS identidades
  probando el acceso cruzado. Documenta como `evidence` en el finding.
- Mapea a `finding.schema.json`: `owasp` (p.ej. `API1:2023-BOLA`), `cwe`, `severity`, `cvss`/`cvss_vector`,
  `target_id`, `evidence`, `reproduction`. `status: candidate` hasta verificar; `confirmed`/`exploited` con prueba.
- No exfiltres datos reales: demuestra excessive-exposure/BOLA con el mínimo (un registro, campos redactados).
- **Redacta el material de autenticación (CRÍTICO):** el par diferencial lleva `Authorization: Bearer …`/
  `Cookie`/api-key VIVOS. Al guardarlos en `evidence[]`/artefactos, sustituye ese header por
  `[REDACTED:identity=<identity_id>]` y referencia la identidad por su `identity_id` (de `identities[]`),
  NUNCA por su token. El token vivo no se escribe jamás en el blackboard: `secret_scan` no caza tokens de
  cliente ahí, así que la redacción es responsabilidad determinista del operador/agente.
- Acciones que tocan el target pasan por el gate humano (tiers en `bot/intel/risk.py`, `approval_mode`).
