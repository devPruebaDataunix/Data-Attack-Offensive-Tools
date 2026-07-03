"""tgfmt.py — Capa de formato Telegram (MarkdownV2). Fuente ÚNICA de estilo del bot.

Análoga a tui/theme.py (que centraliza el COLOR de la TUI): aquí se centraliza el FORMATO de las
respuestas del bot. Todas las respuestas se construyen con estos helpers y se envían con
`parse_mode="MarkdownV2"` — un escaper CORRECTO en un solo sitio, en vez del Markdown legacy + fallback
a texto plano (frágil y feo) que había antes. Sube el listón de calidad de forma consistente.

Contrato (importa respetarlo para no romper el parseo):
  · `esc()`/`esc_code()`/`esc_url()` escapan TEXTO CRUDO para su contexto de MarkdownV2.
  · `bold()`/`italic()`/`code()`/`pre()`/`link()` toman TEXTO CRUDO y devuelven un fragmento MD2 YA escapado.
  · `kv()`/`kv_raw()`/`bullet()`/`lines()`/`card()` COMPONEN fragmentos ya formateados (separadores
    literales seguros). NO vuelvas a escapar un fragmento ya formateado.

Es stdlib puro (no importa `telegram`): 100% testeable sin red (bot/tests/test_tgfmt.py).
"""
from __future__ import annotations

# Metacaracteres que MarkdownV2 EXIGE escapar en texto normal (Telegram Bot API, "MarkdownV2 style").
_SPECIAL = set(r"_*[]()~`>#+-=|{}.!")


def esc(s) -> str:
    """Escapa TEXTO CRUDO para MarkdownV2 (todos los metacaracteres). None -> ''."""
    return "".join("\\" + c if c in _SPECIAL else c for c in ("" if s is None else str(s)))


def esc_code(s) -> str:
    """Escapa para DENTRO de `code`/```pre```: en ese contexto solo hay que escapar '\\' y '`'."""
    return ("" if s is None else str(s)).replace("\\", "\\\\").replace("`", "\\`")


def esc_url(s) -> str:
    """Escapa para la parte (url) de un enlace. La doc de Telegram dice 'solo ) y \\', pero el
    tokenizador REAL también se atraganta con un '(' sin escapar dentro de la URL (rompe el parseo del
    enlace); lo escapamos por robustez. (Aun así, para refs no fiables preferimos code() a link().)"""
    return (("" if s is None else str(s))
            .replace("\\", "\\\\").replace(")", "\\)").replace("(", "\\("))


# ── fragmentos con formato (toman texto CRUDO) ─────────────────────────────────────
def bold(s) -> str:
    return f"*{esc(s)}*"


def italic(s) -> str:
    return f"_{esc(s)}_"


def code(s) -> str:
    return f"`{esc_code(s)}`"


def pre(s, lang: str = "") -> str:
    return f"```{lang}\n{esc_code(s)}\n```"


def link(text, url) -> str:
    return f"[{esc(text)}]({esc_url(url)})"


# ── composición (toman fragmentos YA formateados, NUNCA texto crudo) ────────────────
# REGLA ÚNICA: por debajo de esta línea, el `value`/`fragment`/`body` DEBE ser un fragmento MD2 ya
# escapado (envuélvelo en esc()/code()/bold()/… en el llamador). Pasar texto crudo aquí rompe el parseo.
def kv(label, value) -> str:
    """'*label*: value' — `label` es texto CRUDO (se escapa); `value` es un FRAGMENTO MD2 ya escapado
    (p.ej. `esc(x)`, `code(x)`, un chip). Un solo `kv` (antes había kv/kv_raw): regla única = value=fragmento."""
    return f"{bold(label)}: {value}"


def bullet(fragment, marker: str = "•") -> str:
    """Línea de lista. `fragment` ya es MD2; `marker` debe ser un símbolo seguro (no metacarácter)."""
    return f"{marker} {fragment}"


def lines(*parts) -> str:
    """Une fragmentos MD2 con saltos de línea, omitiendo None/'' y aplanando listas/tuplas."""
    out: list[str] = []
    for p in parts:
        if p is None or p == "":
            continue
        if isinstance(p, (list, tuple)):
            out.extend(x for x in p if x)
        else:
            out.append(p)
    return "\n".join(out)


def card(title, body=None, icon: str = "") -> str:
    """Tarjeta: cabecera en negrita (`title` es texto CRUDO, se escapa; `icon` un símbolo seguro) + cuerpo.
    `body` = lista de FRAGMENTOS MD2, o un ÚNICO fragmento str ya escapado. NO pases texto crudo multilínea
    aquí (se insertaría sin escapar y rompería el parseo): envuelve cada línea en esc()/un helper primero."""
    head = (f"{icon} " if icon else "") + bold(title)
    body_txt = lines(*body) if isinstance(body, (list, tuple)) else (body or "")
    return head + ("\n" + body_txt if body_txt else "")


# ── chips / emojis semánticos ──────────────────────────────────────────────────────
_SEV = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵",
        "info": "⚪", "informational": "⚪", "none": "⚪"}


def sev_emoji(sev) -> str:
    """Emoji por severidad (colorblind-safe: el texto acompaña siempre)."""
    return _SEV.get(str(sev or "").lower(), "⚪")


_MODE_EMOJI = {"full": "🟢", "critical": "🟡", "auto": "🔴"}


def mode_emoji(mode) -> str:
    """Emoji del modo de supervisión humana (full más seguro -> auto menos supervisado)."""
    return _MODE_EMOJI.get(str(mode or "").lower(), "⚪")


# ── degradación (fallback) ─────────────────────────────────────────────────────────
def plain(md2: str) -> str:
    """Degrada un texto MD2 a texto legible si Telegram rechaza el parseo (BadRequest). Quita SOLO las
    barras de escape ('\\.' -> '.'); deja los marcadores (*/_/`) visibles para no PERDER contenido
    (perder un carácter de un dominio/comando sería peor que ver un marcador). Best-effort: con el
    escaper correcto no debería activarse casi nunca."""
    out: list[str] = []
    i, n = 0, len(md2 or "")
    while i < n:
        if md2[i] == "\\" and i + 1 < n and md2[i + 1] in _SPECIAL:
            out.append(md2[i + 1])
            i += 2
        else:
            out.append(md2[i])
            i += 1
    return "".join(out)
