# Guía de estilo visual — Data Attack

Referencia para que el README y la documentación mantengan una imagen coherente. Pensada para
el repo real: agentes de Claude Code, RAG en SQLite, bot de Telegram y despliegue en Kali. No
inventa stack que no usamos.

## 1. Paleta

| Nombre | Hex | Uso |
| :--- | :--- | :--- |
| GitHub Dark | `#0D1117` | Fondo base, `labelColor` de los badges |
| Naranja fuego | `#FF6B35` | Acento principal, títulos, marca |
| Cyan tech | `#00D4FF` | Capacidades, enlaces, tecnología |
| Verde OK | `#3FB950` | Estado correcto, "humano en el bucle", scope guarded |
| Ámbar | `#D29922` | Aviso, licencia, pendiente |
| Rojo alerta | `#FF4444` | Crítico, "uso autorizado únicamente" |
| Blanco GH | `#E6EDF3` | Texto principal |
| Muted | `#8B949E` | Texto secundario |

Acentos del banner: naranja `#FF6B35` sobre fondo oscuro, detalles en cyan. Cualquier gráfico
nuevo respeta esa pareja.

## 2. Badges (shields.io)

Usa **badges estáticos** (`/badge/label-mensaje-color`). El repo es privado, así que los
badges dinámicos que consultan la API de GitHub (stars, release, CI) renderizan "invalid" — no
los pongas.

```markdown
![Etiqueta](https://img.shields.io/badge/LABEL-MENSAJE-COLOR?style=for-the-badge&logo=LOGO&logoColor=white&labelColor=0D1117)
```

- `style=for-the-badge` para la fila de cabecera; `style=flat-square` para las filas de
  capacidades.
- `labelColor=0D1117` siempre.
- Guion en el texto → `--`; espacio → `_`; `+` → `%2B`; tildes → percent-encoding (`%C3%BA`).
- No declares lo que no existe: nada de "tests passing", coverage o CI si no hay workflow real.

## 3. Tipografía y encabezados

- Encabezados en **mayúscula de frase** ("Características clave"), no Tipo Título.
- Un emoji por sección como mucho, y que aporte contexto, no decoración.
- Negrita para el término clave, no para media frase.

## 4. Emojis funcionales

| Contexto | Emoji |
| :--- | :--- |
| Orquestador / hub | 🧭 |
| Agentes / IA | 🤖 🧠 |
| Alcance / seguridad | 🛡️ 🔒 |
| RAG / datos | 📚 🗒️ |
| Bot / móvil | 📱 |
| Aviso legal | ⚠️ |
| Zonas E1 / E2 / E3 | 🟦 🟥 🟩 |

## 5. Callouts

GitHub renderiza alertas nativas — úsalas para lo importante:

```markdown
> [!WARNING]
> Uso autorizado únicamente. Operar fuera de scope es ilegal.

> [!NOTE]
> El RAG corre en SQLite local, sin dependencias externas.
```

## 6. Tablas y secciones plegables

- Tablas para inventarios (agentes, zonas, tiers de riesgo).
- `<details><summary>` para listas largas (los 13 agentes de E2, la aprobación por riesgo),
  así la cabecera del README respira.

## 7. Diagramas

Mermaid se renderiza en GitHub. El diagrama del README sale del estado real y el mapa completo
se autogenera en `ARCHITECTURE_MAP.md` (`python tools/gen_arch_diagram.py`). Si cambias la
arquitectura, regenera el mapa en vez de dibujar a mano.

## 8. Banner

`docs/assets/banner.png` es el banner oficial. Refleja la arquitectura real (hub-and-spoke con
**bus A2A mediado**, 18 agentes, blackboard, scope guard, RAG KEV+EPSS, bot). El wordmark de la
suite es **DATA ATTACK · HARNESS A2A** (`assets/banners/data-attack.txt`). No uses banners que
describan una **malla peer-to-peer directa** (la nativa de Agent Teams es lab-only, ver
`ARCHITECTURE.md §1`) ni un stack de **microservicios** Docker/FastAPI/Redis como *arquitectura*
(el motor son los subagentes de Claude Code; Docker es solo una opción de **despliegue**
reproducible, ver `DEPLOY.md`): no es lo que hace la herramienta.

## 9. Principios

1. Oscuro por defecto sobre `#0D1117`.
2. Naranja para la marca y la acción; cyan para lo técnico.
3. Solo información verificable: si no está en el repo, no va en la imagen.
4. Consistencia de colores, emojis y estructura entre README y docs.
5. Prosa con criterio, no relleno (ver `docs/humanizer-checklist.md`).
