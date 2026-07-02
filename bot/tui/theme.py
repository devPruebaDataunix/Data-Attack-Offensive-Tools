"""
theme.py — Fuente ÚNICA de color de la TUI (tokens de diseño). SIN dependencia de Textual.

Antes el color vivía disperso en ~26 literales hex repartidos entre app.tcss (bordes/fondos) y el
markup Rich de state.py/app.py/panels.py — DOS sistemas de color desincronizados. Aquí se centraliza:
  · las CONSTANTES con nombre las usa el markup Rich de los .py  ->  f"[{DANGER}]…[/]".
  · CSS_VARS las inyecta app.py en el stylesheet (App.get_css_variables) como $brand/$info/… -> app.tcss
    las referencia sin volver a escribir el hex.
Cambiar la paleta = tocar SOLO este fichero.

Paleta = base GitHub-dark (la que la TUI ya usaba: #0d1117/#161b22/#c9d1d9/verde) + el ROJO DataUnix
como marca. Jerarquía: el rojo de marca es identidad + acción (NUNCA 'peligro'); el peligro es un
coral CLARAMENTE distinto; lo informativo es azul (antes el cian neón, que dominaba). El icono
acompaña SIEMPRE al color (colorblind-safe): el significado no depende solo del tono.

Al ser stdlib puro (no importa Textual/Rich), es 100% testeable sin terminal (bot/tests/test_tui.py).
"""
from __future__ import annotations

# ── Tokens de color (hex) — la ÚNICA fuente ────────────────────────────────────────
BRAND = "#e02c41"    # rojo DataUnix: identidad (wordmark), línea de orden, fase activa; NO es 'peligro'
INFO = "#58a6ff"     # azul GitHub: cabeceras de sección + bordes de panel (antes el cian neón #00D4FF)
OK = "#3fb950"       # verde GitHub: éxito / fase completada
WARN = "#d29922"     # ámbar GitHub: aviso / cerca del techo (antes el naranja #FF6B35)
DANGER = "#f85149"   # coral GitHub: error / peligro / techo superado (antes #FF4444; ≠ rojo de marca)
MUTED = "#6e7681"    # gris GitHub: texto atenuado / estados vacíos / pendiente
FG = "#c9d1d9"       # texto de cuerpo
BG = "#0d1117"       # fondo de la app
SURFACE = "#161b22"  # paneles elevados / cabecera / modal

# Nombres de variable CSS ($brand, $info, …) que app.py inyecta en el stylesheet (get_css_variables).
# Son CUSTOM y namespaced: NO pisan las variables propias de Textual ($primary/$accent/$success/…).
CSS_VARS: dict[str, str] = {
    "brand": BRAND, "info": INFO, "ok": OK, "warn": WARN, "danger": DANGER,
    "muted": MUTED, "fg": FG, "bg": BG, "surface2": SURFACE,
}


# ── Primitivas de markup Rich (una sola definición, reutilizable) ──────────────────
def panel_title(text: str) -> str:
    """Cabecera de sección (azul info, negrita). Una sola definición en vez de repetir
    '[b #hex]…[/]' por toda la UI — cambiar el look de las cabeceras = tocar solo aquí.
    `text` es un literal estático de la UI (no dato del blackboard); no requiere escape."""
    return f"[b {INFO}]{text}[/]"


def finding_bucket(kind: str) -> tuple[str, str]:
    """(icono, color) de un bucket de hallazgos (classify: real/watch/noise). Colorblind-safe:
    el ICONO (forma) desambigua aunque no se distinga el color —
    ● sólido = real (peligro) · ▲ = vigilar (aviso) · · = ruido (atenuado)."""
    return {
        "real": ("●", DANGER),
        "watch": ("▲", WARN),
        "noise": ("·", MUTED),
    }.get(kind, ("·", MUTED))
