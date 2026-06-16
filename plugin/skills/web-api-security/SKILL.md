---
name: web-api-security
description: Metodología de pentest de APIs (REST/GraphQL) — BOLA/IDOR, BFLA, mass assignment, fuga de datos masiva, rate-limit y SSRF vía API. Úsala cuando el activo en scope exponga una API, rutas /api, swagger/openapi.json o un endpoint GraphQL.
---

# Seguridad ofensiva de APIs (REST / GraphQL)

Las APIs son hoy el vector #1: el fallo no suele estar en la inyección clásica sino en la
**autorización a nivel de objeto y de función**. Mapea contra OWASP API Security Top 10.

## Cuándo usarla
Tras descubrir una API en scope (rutas `/api`, `/v1`, `graphql`, `swagger`/`openapi.json`,
cabeceras `Authorization: Bearer`). Antes de explotar, confirma alcance en `contracts/scope.json`.

## Técnicas (con MITRE)
- **BOLA / IDOR** (T1190): cambia el identificador de objeto (`/users/123` → `124`, UUIDs en
  el body) con el token de un usuario de menor privilegio. Es la causa de >50% de brechas API.
- **BFLA** (broken function-level auth): llama a endpoints administrativos (`/admin`, `DELETE`,
  métodos no enlazados en la UI) con un rol bajo.
- **Mass assignment**: inyecta campos no previstos en el JSON (`"role":"admin"`, `"isVerified":true`).
- **Excessive data exposure**: la API devuelve más campos de los que la UI muestra (PII, hashes).
- **GraphQL**: introspección (`__schema`), batching/alias para saltar rate-limit, IDOR por nodo.
- **SSRF vía API** (T1190): parámetros tipo `url=`, `webhook=`, `image_url=` → pivot interno.

## Herramientas (suite del repo)
- Descubrimiento de endpoints: `recon-suite` (`httpx`, `katana`, `gau`) — tier **normal**.
- Fuzzing de rutas/parámetros: `web-fuzzing` (`ffuf`, `feroxbuster`) — tier **normal**.
- Plantillas: `nuclei` (tags `exposure`, `graphql`, `swagger`) — tier **normal**.
- Inyección: `sqlmap` sobre parámetros de la API — tier **sensitive** (pide aprobación).
- Captura/replay manual con proxy (Burp/mitmproxy) para BOLA/BFLA.

## Evidencia y alcance
- **Sin fuente no se explota**: un IDOR es finding solo con la petición + respuesta que prueba
  el acceso cruzado. Documenta request/response como `evidence` en `contracts/engagement.json`.
- Mapea a `contracts/finding.schema.json` (`title`, `severity`, `cvss`/`cvss_vector`, `target_id`,
  `evidence`, `reproduction`). `status: candidate` hasta verificarlo; `confirmed`/`exploited` con prueba.
- Acciones que tocan el target pasan por el gate humano del bot (tiers en `bot/intel/risk.py`).
