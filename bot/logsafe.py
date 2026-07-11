"""logsafe — evita que el token del bot (u otros secretos) acabe en los logs.

La API de Telegram mete el token en la RUTA de la URL (…/bot<TOKEN>/getUpdates), y el cliente HTTP
(httpx, por debajo de python-telegram-bot) registra CADA petición a nivel INFO. Con el root logger en
INFO, eso escribe el token en claro en bot.log en cada poll. Aquí lo cerramos por dos vías:
  · `quiet_http_loggers()` — sube httpx/httpcore a WARNING: corta de raíz el log INFO por-petición que
    incluye el token (evita GENERARLO).
  · `RedactFilter` / `redact_secrets()` — filtro que reescribe el mensaje YA formateado de cada registro
    enmascarando el token (literal + patrón). Defensa EN PROFUNDIDAD: tapa cualquier ruta que aún colara
    el token (p. ej. un WARNING/ERROR de httpx que incluya la URL), venga de donde venga.

stdlib puro (no importa `telegram`): 100% testeable sin red (bot/tests/test_logsafe.py).
"""
from __future__ import annotations

import logging
import re
import traceback

# Token de Telegram: en URL (…/bot<id>:<secret>/…) o suelto (<id>:<secret>). id 6+ dígitos; secreto 30+.
_TOKEN_RE = re.compile(r"(?:bot)?\d{6,}:[A-Za-z0-9_-]{30,}")
_MASK = "[REDACTED]"   # ASCII a propósito: el log se escribe en la codificación local (bot.log), sin mojibake


def redact_secrets(text, token: str = "") -> str:
    """Enmascara el token del bot en `text`: primero el valor LITERAL (si se conoce, lo más fiable) y
    luego el PATRÓN genérico (por si aparece con otra forma). None -> ''. Puro y testeable."""
    out = "" if text is None else str(text)
    if token:
        out = out.replace(token, _MASK)
    return _TOKEN_RE.sub(_MASK, out)


class RedactFilter(logging.Filter):
    """Filtro de logging que reescribe el mensaje ya formateado de cada registro con el token enmascarado.
    Enganchado a los handlers del root, cubre TODOS los loggers (httpx, telegram y los nuestros)."""

    def __init__(self, token: str = ""):
        super().__init__()
        self._token = token or ""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - un formateo roto jamás debe tumbar el logging
            return True
        red = redact_secrets(msg, self._token)
        if red != msg:
            record.msg = red
            record.args = ()
        # El TRACEBACK de exc_info lo formatea el Formatter aparte (formatException), DESPUÉS del mensaje y
        # SIN pasar por los filtros: una excepción de httpx cuyo str() lleva la URL con el token (p. ej. en
        # los `log.exception` de bot.py ante un fallo de red durante una orden) filtraría el token en el
        # traceback. Lo renderizamos ya REDACTADO y lo cacheamos en `exc_text`: Formatter.format() respeta
        # exc_text si no es None (no lo recomputa). Idempotente entre handlers (el 2º ve exc_text ya puesto).
        if record.exc_info and not record.exc_text:
            try:
                rendered = "".join(traceback.format_exception(*record.exc_info))
                record.exc_text = redact_secrets(rendered, self._token)
            except Exception:  # noqa: BLE001 - formatear un traceback jamás debe tumbar el logging
                pass
        return True


def _quiet_http_loggers(level: int = logging.WARNING) -> None:
    """Sube httpx/httpcore a WARNING para que no emitan el log INFO por-petición (que lleva el token)."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(level)


def install(token: str = "") -> None:
    """Instala la protección completa: silencia los loggers HTTP y añade RedactFilter a los handlers del
    root. Llamar UNA vez tras logging.basicConfig() y DESPUÉS de configurar los handlers del root — solo
    protege los handlers que existen en el momento de la llamada (los añadidos luego no quedan cubiertos)."""
    _quiet_http_loggers()
    root = logging.getLogger()
    flt = RedactFilter(token)
    for h in root.handlers:
        h.addFilter(flt)
