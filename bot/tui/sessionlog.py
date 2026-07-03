"""
sessionlog.py — Log de sesión PERSISTENTE de la narración (F0).

Motivación (root-cause del cuelgue de la TUI, 3-jul): la narración de la TUI vivía SOLO en el
RichLog en memoria y se PERDÍA al reiniciar, mientras el estado en disco (contracts/.action_count,
contracts/engagement.json) SÍ persiste → tras un cuelgue/reinicio el registro salía vacío aunque las
"acciones 8/1000" seguían. Este módulo persiste cada línea de narración a
`engagements/<id>/session.log` (JSONL) para que la TUI la REPRODUZCA al arrancar y el histórico
sobreviva a reinicios.

Diseño:
  · Por-engagement: `engagements/<id>/session.log`. `engagements/` está gitignored → el histórico
    queda AISLADO por cliente (zona E3) y nunca se commitea. `_safe_id` es INYECTIVO (ids distintos
    -> carpetas distintas) para que dos clientes jamás compartan log por colapso de saneo.
  · JSONL `{"ts": <unix>, "text": <str>}`: `text` es la línea TAL CUAL la escribe el front-end (la
    TUI pasa markup Rich; un consumidor plano usa `strip_markup()`). Formato-agnóstico a propósito.
  · REDACCIÓN de secretos ANTES de escribir (control C12, OWASP LLM02). La narración es texto libre
    del Orquestador y podría incrustar un secreto en claro (un `hashdump`, "password: X"). Como este
    log PERSISTE a disco (antes vivía y moría en RAM), cada línea pasa por `tools/redactor.redact()`
    en `append()`: así este sumidero nuevo queda cubierto por el mismo invariante que imponen los
    hooks `secret_scan`/`memory_guard` sobre el blackboard. NUNCA se persiste un secreto del operador.
  · Best-effort: NUNCA lanza. Un fallo de logging jamás debe tumbar una orden (se traga OSError).
  · **SINGLE-WRITER (hoy solo escribe la TUI).** `append` no toma lock: `open("a")` no garantiza
    atomicidad entre procesos en Windows y `_prune` (read→write→replace) puede pisar un append
    concurrente. El FORMATO ya sirve para múltiples LECTORES (bot/dashboard), pero habilitar un
    segundo ESCRITOR exige antes un lock de fichero (`fcntl.flock`/`msvcrt.locking`). No conectes el
    bot/dashboard como escritores sin ese lock.
  · stdlib puro (+ `tools/redactor`, también stdlib) → 100% testeable en bot/tests/test_sessionlog.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

# Caps de crecimiento. `engagements/` está gitignored y aislado por cliente → el disco NO es la
# restricción; un engagement Red Team real (horas/días) emite decenas de miles de líneas y las
# queremos como registro forense. La poda es solo red anti-desbordamiento patológico, no rotación
# agresiva. Jerarquía deliberada de caps: fichero (forense, KEEP_LINES) ≥ RichLog en RAM (2000,
# ventana viva; app.py:228) ≥ replay al arrancar (DEFAULT_TAIL).
MAX_BYTES = 25_000_000        # ~25 MB antes de podar
KEEP_LINES = 50_000           # conserva las últimas ~50k líneas (registro forense amplio)
DEFAULT_TAIL = 500            # líneas que la TUI reproduce al arrancar
_TAIL_READ_BYTES = 2_000_000  # `tail` lee como mucho los últimos ~2 MB → arranque rápido aun con log enorme

# Nombres de dispositivo reservados de Windows: `engagements/nul/` resolvería al dispositivo NUL y la
# escritura se perdería EN SILENCIO (justo el fallo mudo que F0 quería eliminar). El repo corre en Win11.
_WIN_RESERVED = {"con", "prn", "aux", "nul",
                 *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}

# Etiquetas de markup Rich a quitar para un consumidor plano: apertura `[b]`/`[b #e02c41]`/`[#hex]`,
# cierre `[/b]` y cierre-total `[/]`. El lookbehind `(?<!\\)` respeta el corchete literal que
# state._esc escribe como `\[` (no lo confunde con una etiqueta).
_MARKUP = re.compile(r"(?<!\\)\[/?(?:[a-zA-Z#][^\[\]]*)?\]")

# Redactor de secretos: MISMA fuente que los hooks (control C12). Import robusto bot/tui/ -> repo/tools/.
try:
    _TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)
    from redactor import redact as _redact_full   # type: ignore  # noqa: E402
except Exception:   # pragma: no cover - redactor.py es un fichero del repo; esto es solo un suelo
    _redact_full = None

# Suelo mínimo si el redactor no fuese importable: los secretos del OPERADOR/motor que JAMÁS deben
# persistir (clave privada, API key de Anthropic, token del bot). Reflejo de los patrones op_only.
_MIN_SECRETS = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    r"|sk-ant-[A-Za-z0-9_\-]{20,}"
    r"|\b\d{8,10}:[A-Za-z0-9_-]{35}\b")


def _hash8(s: str) -> str:
    """Hash corto y estable de un id (para desambiguar carpetas de forma inyectiva)."""
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:8]


def _redact(text: str) -> str:
    """Redacta secretos ANTES de persistir. Usa el redactor determinista del repo; si (por lo que
    sea) no es importable, aplica el suelo mínimo de secretos del operador. Nunca lanza."""
    if _redact_full is not None:
        try:
            return _redact_full(text)
        except Exception:
            pass
    return _MIN_SECRETS.sub("[REDACTED]", text)


def _safe_id(engagement_id) -> str:
    """Sanitiza el engagement_id para usarlo como nombre de carpeta (defensa anti path-traversal: el
    id viene de engagement.json —que controlamos— pero nunca se construye una ruta con datos sin
    limpiar). Deja solo [A-Za-z0-9._-]; el resto -> '_'.

    INYECTIVO: si el saneo altera el id (dos ids distintos podrían colapsar a la MISMA carpeta ->
    mezcla de narración entre clientes = fuga E3) o el nombre coincide con un dispositivo reservado
    de Windows, añade un sufijo `-<hash8>` del id ORIGINAL. Así ids distintos nunca comparten log, y
    un id ya limpio conserva su nombre (co-ubicado con los artefactos de `engagements/<id>/`)."""
    raw = str(engagement_id or "")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", raw).strip("._")
    if not safe:
        return "sesion" if not raw else "sesion-" + _hash8(raw)
    reserved = safe.split(".")[0].lower() in _WIN_RESERVED
    if safe != raw or reserved:
        return f"{safe}-{_hash8(raw)}"
    return safe


def log_path(repo, engagement_id) -> Path:
    """Ruta del log de sesión del engagement dado."""
    return Path(repo) / "engagements" / _safe_id(engagement_id) / "session.log"


def append(repo, engagement_id, text, *, ts: float | None = None) -> None:
    """Añade una línea de narración al log de sesión del engagement. Best-effort: nunca lanza.
    Redacta secretos ANTES de escribir. No-op si falta engagement_id (narración pre-engagement =
    efímera a propósito) o text es None."""
    if not engagement_id or text is None:
        return
    path = log_path(repo, engagement_id)
    rec = json.dumps({"ts": time.time() if ts is None else float(ts), "text": _redact(str(text))},
                     ensure_ascii=False)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(rec + "\n")
        if path.stat().st_size > MAX_BYTES:
            _prune(path)
    except OSError:
        pass   # un fallo de disco no debe romper la narración ni la orden en curso


def _prune(path: Path) -> None:
    """Poda el log a las últimas KEEP_LINES líneas (reescritura atómica). Best-effort. Usa
    `split("\\n")` (no `splitlines()`) para no partir registros por separadores Unicode raros
    (\\u2028/\\u2029 que json.dumps no escapa y podrían aparecer en output ofensivo)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        if lines and lines[-1] == "":
            lines.pop()                 # el "" tras el último \n no es una línea
        if len(lines) <= KEEP_LINES:
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(lines[-KEEP_LINES:]) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def tail(repo, engagement_id, n: int = DEFAULT_TAIL) -> list[dict]:
    """Últimas `n` entradas `{"ts","text"}` del log de sesión (todas si n<=0). [] si no existe o está
    corrupto; salta líneas ilegibles. Nunca lanza. Lee como mucho los últimos `_TAIL_READ_BYTES`
    (arranque O(1) aunque el log forense sea enorme); descarta la 1ª línea leída si el fichero se
    truncó por el offset (probable línea a medias)."""
    path = log_path(repo, engagement_id)
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            truncated = size > _TAIL_READ_BYTES
            if truncated:
                fh.seek(size - _TAIL_READ_BYTES)
            data = fh.read()
        raw = data.decode("utf-8", errors="replace").split("\n")
        if raw and raw[-1] == "":
            raw.pop()                   # el "" tras el último \n no es una línea (no gasta hueco en [-n:])
        if truncated and raw:
            raw = raw[1:]               # la 1ª línea puede venir cortada por el offset
    except OSError:
        return []
    out: list[dict] = []
    for line in (raw[-n:] if n and n > 0 else raw):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and "text" in rec:
            out.append({"ts": rec.get("ts"), "text": str(rec.get("text", ""))})
    return out


def strip_markup(text) -> str:
    """Quita el markup Rich de una línea (para consumidores planos: bot/dashboard). Es la reversa del
    escape de state._esc: primero borra las etiquetas `[..]`, luego destapa el `\\[` literal.
    Pragmático: no pretende cubrir markup Rich arbitrario, solo el que emite esta TUI."""
    return _MARKUP.sub("", str(text or "")).replace("\\[", "[")


def fmt_clock(ts) -> str:
    """HH:MM:SS local de un ts unix (prefijo del histórico reproducido). '' si no es un ts válido."""
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return ""
