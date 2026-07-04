#!/usr/bin/env python3
"""
Tests del log de sesión persistente (bot/tui/sessionlog.py, F0): round-trip append/tail, aislamiento
por-engagement, poda por tamaño, saneo anti-traversal, strip_markup y robustez (best-effort, nunca
lanza). stdlib puro (sin Textual/Rich/telegram), 100% testeable sin terminal ni red.

Corre standalone:  python bot/tests/test_sessionlog.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from tui import sessionlog as SL   # noqa: E402


def _tmp():
    return tempfile.mkdtemp(prefix="dataattack-sesslog-")


def test_append_tail_roundtrip_preserves_order_and_ts():
    repo = _tmp()
    try:
        SL.append(repo, "eng-1", "primera", ts=100.0)
        SL.append(repo, "eng-1", "segunda", ts=101.0)
        SL.append(repo, "eng-1", "tercera", ts=102.0)
        got = SL.tail(repo, "eng-1")
        assert [e["text"] for e in got] == ["primera", "segunda", "tercera"]
        assert got[0]["ts"] == 100.0 and got[2]["ts"] == 102.0
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_tail_limit_returns_only_last_n():
    repo = _tmp()
    try:
        for i in range(10):
            SL.append(repo, "eng-1", f"linea-{i}", ts=float(i))
        got = SL.tail(repo, "eng-1", n=3)
        assert [e["text"] for e in got] == ["linea-7", "linea-8", "linea-9"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_tail_missing_engagement_is_empty():
    repo = _tmp()
    try:
        assert SL.tail(repo, "no-existe") == []
        assert SL.tail(repo, "") == []
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_append_is_noop_without_engagement_or_text():
    repo = _tmp()
    try:
        SL.append(repo, "", "algo")            # sin engagement -> efímero a propósito
        SL.append(repo, None, "algo")
        SL.append(repo, "eng-1", None)         # text None -> no escribe
        assert SL.tail(repo, "eng-1") == []
        assert not os.path.exists(SL.log_path(repo, "eng-1"))
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_engagements_are_isolated_per_id():
    repo = _tmp()
    try:
        SL.append(repo, "cliente-A", "solo-A", ts=1.0)
        SL.append(repo, "cliente-B", "solo-B", ts=1.0)
        assert [e["text"] for e in SL.tail(repo, "cliente-A")] == ["solo-A"]
        assert [e["text"] for e in SL.tail(repo, "cliente-B")] == ["solo-B"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_safe_id_blocks_path_traversal():
    # Un engagement_id malicioso NUNCA debe escapar de engagements/.
    sid = SL._safe_id("../../etc/passwd")
    assert ".." not in sid and "/" not in sid and "\\" not in sid
    p = SL.log_path("/repo", "../../etc/passwd")
    parts = p.parts
    assert "engagements" in parts and ".." not in parts
    # el id vacío cae a un nombre por defecto seguro; el degenerado, a uno único pero seguro
    assert SL._safe_id("") == "sesion"
    assert SL._safe_id("...").startswith("sesion") and ".." not in SL._safe_id("...")


def test_safe_id_is_injective_across_colliding_ids():
    # Dos ids que SANEAN al mismo string pero difieren en crudo -> carpetas DISTINTAS (aislamiento E3):
    # sin esto, cliente/A y cliente:A compartirían session.log y se mezclaría su narración.
    a = SL._safe_id("cliente/A")
    b = SL._safe_id("cliente:A")
    c = SL._safe_id("cliente_A")
    assert a != b and b != c and a != c
    assert "/" not in a and ":" not in a and "\\" not in a


def test_safe_id_suffixes_windows_reserved_names():
    # engagements/nul/ apuntaría al dispositivo NUL (Win) y perdería la narración sin error.
    for name in ("nul", "CON", "com1", "LPT9", "aux"):
        sid = SL._safe_id(name)
        assert sid.lower() != name.lower()
        assert sid.lower().startswith(name.lower() + "-")


def test_append_redacts_operator_secrets():
    # F0 persiste a disco lo que antes moría en RAM -> DEBE redactar secretos del operador antes.
    repo = _tmp()
    try:
        akey = "sk-ant-" + "A" * 30
        SL.append(repo, "eng-1", f"logre acceso con {akey} en claro", ts=1.0)
        SL.append(repo, "eng-1", "-----BEGIN OPENSSH PRIVATE KEY-----", ts=2.0)
        blob = "\n".join(e["text"] for e in SL.tail(repo, "eng-1"))
        assert akey not in blob                 # el secreto NO se persiste en claro
        assert "PRIVATE KEY" not in blob        # la clave privada tampoco
        assert "[REDACTED" in blob              # se sustituye por marcador
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_tail_bounded_read_keeps_recent():
    # `tail` acota la lectura a los últimos _TAIL_READ_BYTES -> arranque O(1) aun con log enorme.
    repo = _tmp()
    orig = SL._TAIL_READ_BYTES
    SL._TAIL_READ_BYTES = 120                   # fuerza lectura acotada (descarta la 1ª línea, posible corte)
    try:
        for i in range(20):
            SL.append(repo, "eng-1", f"L{i}", ts=float(i))
        got = [e["text"] for e in SL.tail(repo, "eng-1", n=1000)]
        assert got and got[-1] == "L19"         # conserva SIEMPRE lo más reciente
        assert "L0" not in got                  # lo viejo cae fuera de la ventana de bytes
    finally:
        SL._TAIL_READ_BYTES = orig
        shutil.rmtree(repo, ignore_errors=True)


def test_prune_caps_growth_keeping_the_tail():
    repo = _tmp()
    orig_bytes, orig_keep = SL.MAX_BYTES, SL.KEEP_LINES
    SL.MAX_BYTES, SL.KEEP_LINES = 200, 5   # fuerza poda temprana
    try:
        for i in range(60):
            SL.append(repo, "eng-1", f"msg-{i}", ts=float(i))
        got = SL.tail(repo, "eng-1", n=1000)
        # La poda acota el crecimiento: de 60 líneas queda un puñado (KEEP_LINES, +1 si el último
        # append aún no rebasó MAX_BYTES) — nunca crece sin límite...
        assert len(got) <= SL.KEEP_LINES + 1
        assert len(got) < 60
        assert got[-1]["text"] == "msg-59"             # ...y conserva SIEMPRE lo más RECIENTE
        assert got[0]["text"] != "msg-0"               # (lo antiguo se descartó)
    finally:
        SL.MAX_BYTES, SL.KEEP_LINES = orig_bytes, orig_keep
        shutil.rmtree(repo, ignore_errors=True)


def test_tail_skips_corrupt_lines():
    repo = _tmp()
    try:
        SL.append(repo, "eng-1", "buena-1", ts=1.0)
        path = SL.log_path(repo, "eng-1")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{esto no es json valido\n")       # línea corrupta en medio
        SL.append(repo, "eng-1", "buena-2", ts=2.0)
        assert [e["text"] for e in SL.tail(repo, "eng-1")] == ["buena-1", "buena-2"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_append_concurrent_writers_no_loss():
    # F4: con el lock de fichero (_file_lock), varios ESCRITORES concurrentes (TUI+bot+dashboard sobre el
    # MISMO session.log) no se pisan -> ninguna línea se pierde ni queda a medias (JSON corrupto).
    import threading
    repo = _tmp()
    try:
        n_writers, per = 8, 40
        expected = {f"w{w}-{i}" for w in range(n_writers) for i in range(per)}

        def worker(w):
            for i in range(per):
                SL.append(repo, "eng-1", f"w{w}-{i}", ts=float(i))

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        got = SL.tail(repo, "eng-1", n=1_000_000)
        assert len(got) == n_writers * per                 # nada perdido ni descartado por corrupción
        assert {e["text"] for e in got} == expected        # y exactamente las líneas esperadas
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_file_lock_best_effort_never_raises():
    # El lock es best-effort: aunque el locking del SO no estuviese disponible, append no debe romper.
    repo = _tmp()
    orig_fcntl, orig_msvcrt = SL._fcntl, SL._msvcrt
    SL._fcntl, SL._msvcrt = None, None                     # simula un SO sin locking
    try:
        SL.append(repo, "eng-1", "sin-lock", ts=1.0)
        assert [e["text"] for e in SL.tail(repo, "eng-1")] == ["sin-lock"]
    finally:
        SL._fcntl, SL._msvcrt = orig_fcntl, orig_msvcrt
        shutil.rmtree(repo, ignore_errors=True)


def test_strip_markup_removes_rich_tags():
    assert SL.strip_markup("[b #e02c41]▶ orden[/] lanzada") == "▶ orden lanzada"
    assert SL.strip_markup("[/]") == ""
    assert SL.strip_markup("[b]x[/b]") == "x"
    assert SL.strip_markup("sin markup") == "sin markup"
    assert SL.strip_markup(None) == ""


def test_strip_markup_respects_escaped_literal_bracket():
    # state._esc convierte '[' en '\\[' (corchete literal): strip_markup NO debe tratarlo como etiqueta.
    assert SL.strip_markup("valor \\[raro]") == "valor [raro]"


def test_fmt_clock_valid_and_invalid():
    out = SL.fmt_clock(1_700_000_000.0)
    assert len(out) == 8 and out.count(":") == 2         # HH:MM:SS
    assert SL.fmt_clock(None) == "" and SL.fmt_clock("nope") == ""


# ── runner standalone ───────────────────────────────────────────────────────────
def _all_tests():
    return [(n, f) for n, f in sorted(globals().items())
            if n.startswith("test_") and callable(f)]


def main():
    failed = 0
    for name, fn in _all_tests():
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    total = len(_all_tests())
    print(f"\n  {total - failed}/{total} OK" + ("" if not failed else f"  · {failed} FALLOS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
