"""
commands.py — Paleta de comandos de DOMINIO en español (Textual CommandProvider) de la TUI.

Reemplaza la paleta por defecto de Textual (genérica y en inglés: Keys/Quit/Theme/Screenshot…) por
comandos de DOMINIO en español: navegar a cada pestaña, refrescar, kill-switch, refrescar el RAG,
escribir una orden y cambiar la supervisión. NO relaja ninguna puerta: cada comando es un ATAJO a una
acción que ya existe en la app (que sigue pasando por scope/budget/aprobación cuando toca al target).

El CATÁLOGO (`command_specs`) es LÓGICA PURA y se testea en bot/tests/test_tui.py; el envoltorio
Textual (Provider/search/discover) SOLO se renderiza en Kali, por eso su import es opcional aquí
(en el Windows de desarrollo Textual no está instalado y el catálogo debe seguir importándose).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import actions as A


@dataclass(frozen=True)
class CommandSpec:
    """Un comando de la paleta. `key` es el identificador ESTABLE que despacha la app
    (`DataAttackTUI.run_palette_command`); `title`/`help` son lo que ve el operador (en español)."""
    key: str
    title: str
    help: str


# Pestañas de la TUI (id de TabPane en app.py::compose → etiqueta española). Debe casar con la app.
TABS: list[tuple[str, str]] = [
    ("tab-dash", "Panel"),
    ("tab-a2a", "Bus A2A"),
    ("tab-roster", "Agentes"),
    ("tab-net", "Red"),
    ("tab-budget", "Presupuesto"),
    ("tab-rag", "RAG"),
    ("tab-ev", "Evidencia"),
    ("tab-act", "Acciones"),
]

# Glosa en español de cada modo de supervisión. Las claves DEBEN ser las de actions.APPROVAL_MODES
# (lo verifica un test); el comando fija el valor canónico del enum (full/critical/auto).
_APPROVAL_HELP: dict[str, str] = {
    "full": "aprueba cada acción que toca el target (supervisión máxima)",
    "critical": "solo pide OK en las acciones críticas (por defecto)",
    "auto": "autónomo, sin modales (los guards deterministas siguen activos)",
}


def command_specs() -> list[CommandSpec]:
    """Catálogo PURO de comandos de dominio (sin Textual; testeable en Windows)."""
    specs: list[CommandSpec] = []
    # Navegación: una entrada por pestaña.
    for tab_id, label in TABS:
        specs.append(CommandSpec(f"tab:{tab_id}", f"Ir a: {label}",
                                 f"Muestra la pestaña «{label}»."))
    # Acciones del panel.
    specs.append(CommandSpec("refresh", "Refrescar estado",
                             "Relee el blackboard y el estado de los RAG."))
    specs.append(CommandSpec("focus-cmd", "Escribir una orden al Orquestador",
                             "Salta a la línea de orden para teclear una instrucción."))
    specs.append(CommandSpec("abort", "Kill-switch: abortar la orden en curso",
                             "Aborta la orden activa y deniega toda acción pendiente."))
    specs.append(CommandSpec("rag-refresh", "Refrescar el RAG de vulnerabilidades",
                             "Actualiza CVE/KEV/EPSS/exploits (puede tardar)."))
    specs.append(CommandSpec("rag-refresh-epss", "Refrescar el RAG (recalcular todo el EPSS)",
                             "Refresco completo recalculando los scores EPSS."))
    # Supervisión: una entrada por modo (mismos valores que actions.APPROVAL_MODES).
    for mode in A.APPROVAL_MODES:
        gloss = _APPROVAL_HELP.get(mode, "")
        specs.append(CommandSpec(f"approval:{mode}", f"Supervisión: {mode}",
                                 f"Fija el modo de aprobación a «{mode}»" + (f" — {gloss}." if gloss else ".")))
    specs.append(CommandSpec("quit", "Salir del panel de control",
                             "Cierra la TUI (no afecta a un engagement en curso en la Kali)."))
    return specs


# ── Envoltorio Textual (solo Kali). Import OPCIONAL: en Windows sin Textual el módulo se importa
#    igual y el catálogo puro de arriba queda disponible para los tests. ─────────────────────────
try:
    from functools import partial

    from textual.command import DiscoveryHit, Hit, Hits, Provider

    class DataAttackCommands(Provider):
        """Alimenta la paleta (Ctrl+P) con los comandos de dominio; los ejecuta la app."""

        def _command(self, key: str):
            # La app (DataAttackTUI) resuelve la clave → acción concreta.
            return partial(self.app.run_palette_command, key)

        async def discover(self) -> Hits:
            # Se muestran al abrir la paleta (query vacía).
            for spec in command_specs():
                yield DiscoveryHit(spec.title, self._command(spec.key), help=spec.help)

        async def search(self, query: str) -> Hits:
            matcher = self.matcher(query)
            for spec in command_specs():
                # Empareja por título Y ayuda (encontrar por palabras clave de la descripción); se
                # resalta el título (si el match cayó en la ayuda, la fila igual aparece).
                score = matcher.match(f"{spec.title} {spec.help}")
                if score > 0:
                    yield Hit(score, matcher.highlight(spec.title),
                              self._command(spec.key), help=spec.help)

except ModuleNotFoundError:  # Windows de desarrollo: Textual no está. El catálogo puro sigue usable.
    DataAttackCommands = None  # type: ignore[assignment,misc]
