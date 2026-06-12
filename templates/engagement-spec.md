<!-- Plantilla del BRIEF del engagement (el "qué" y "por qué", legible por humanos).
     Es el paso previo a contracts/scope.json (el "qué" ejecutable que aplica scope_guard).
     Adaptado del `/specify` de spec-driven development. Rellena y revisa con el cliente. -->

# Brief del engagement — {CLIENTE}

> **Estado:** borrador | aprobado · **Engagement ID:** {ACME-2026-001} · **Fecha:** {YYYY-MM-DD}

## 1. Autorización
- **Tipo:** {contrato de pentest | programa de bug bounty}
- **Referencia / SOW:** {SOW-2026-0042}
- **Firmado por:** {ciso@cliente} · **Vigencia:** {YYYY-MM-DD} → {YYYY-MM-DD}
- **ROE (documento):** {enlace/ref interno}

## 2. Objetivos (el "por qué")
Qué quiere demostrar/proteger el cliente, en lenguaje de negocio. Ej.: _"validar que un atacante
externo no puede acceder a datos de clientes a través de la aplicación web pública"_.
- {objetivo 1}
- {objetivo 2}

## 3. Alcance (el "qué")
> Esto se materializa, literal, en `contracts/scope.json`, que es lo que el hook `scope_guard.py`
> aplica en cada acción. El brief explica; `scope.json` ejecuta. **Deben coincidir.**

**En alcance:** dominios `{cliente.com, *.cliente.com}` · IPs `{203.0.113.10}` · CIDR
`{198.51.100.0/24}` · URLs `{https://app.cliente.com}`.
**Fuera de alcance:** {corp.cliente.com, vpn.cliente.com, infra de terceros/correo}.

## 4. Reglas de enfrentamiento (ROE)
- **Ventana de pruebas:** {00:00–06:00 UTC}
- **Rate / agresividad:** {moderado; sin escaneos masivos en horario laboral}
- **Prohibido:** DoS · ingeniería social {sí/no} · exfiltración real (siempre simulada/canary)
- **Contactos:** técnico {nombre/tel} · escalado de incidentes {nombre/tel}

## 5. Restricciones y supuestos
- {p.ej. cuenta AWS compartida — no tocar recursos no listados}
- {credenciales de prueba proporcionadas: sí/no}

## 6. Criterios de éxito y entregables
- **Éxito =** {objetivos 1–2 verificados con evidencia, dentro de scope y ROE}.
- **Entregables:** informe profesional (`report/INFORME-{engagement_id}.md`), resumen de hallazgos,
  evidencia redactada, hoja de remediación.

## 7. Clarificaciones pendientes
Preguntas abiertas a resolver con el cliente **antes** de operar (paso "clarify"):
- [ ] {¿la API móvil entra en alcance?}
- [ ] {¿hay WAF que deba considerarse?}

---
*Tras aprobar este brief: copia `contracts/scope.example.json` → `contracts/scope.json` y rellénalo
con el §3, ejecuta `python tools/analyze_engagement.py` para comprobar coherencia, y arranca el
Orquestador. Ver `docs/engagement-driven.md`.*
