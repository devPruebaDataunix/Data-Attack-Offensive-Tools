#!/usr/bin/env python3
"""
http_proxy.py — PROXY HTTP con ENFORCEMENT DE SCOPE + logging (mejora v2.60; idea de strix, Apache-2.0 →
reimplementación limpia, solo stdlib). Un proxy de reenvío por el que `web-exploit`/`api-exploit` (y el
navegador de la mejora C) encaminan su tráfico dentro del ANILLO efímero: (1) DEJA CONSTANCIA de cada
request/response en un transcript replayable para evidencia/diff, y (2) es un PUNTO DE CONTROL DE SCOPE —
rechaza (403) cualquier request/CONNECT a un host FUERA de scope, cinturón sobre `scope_guard` (que solo
ve el comando externo, no cada request que la herramienta dispara).

NO es un proxy abierto: solo alcanza hosts EN SCOPE, escucha en LOOPBACK y corre en el anillo sin egress
salvo la red-lab. Fail-CLOSED: sin `scope.json` no arranca.

Seguridad:
- **Scope como choke point.** Cada request absoluta y cada `CONNECT host:port` se valida con
  `acquire_session.in_scope` (misma semántica que el gate `scope_guard`); fuera de scope → 403 + registro
  `blocked`. No relaja el scope: da transporte y trazabilidad, no alcance nuevo.
- **HTTPS por CONNECT = túnel ciego.** No hay MITM ni CA: el CONNECT se valida por scope y se tuneliza a
  ciegas (no se descifra TLS). Del HTTPS solo se registran los metadatos de conexión (host/puerto/ts); del
  HTTP en claro se registra la transacción. Honesto y sin la responsabilidad de una CA en el anillo.
- **Transcript redactado y confinado (E3).** Va SOLO a `engagements/<id>/exploit/` (gitignored). Las
  cabeceras sensibles (Authorization/Cookie/…) se redactan enteras; el resto de valores y los cuerpos
  (truncados) pasan por `redactor.redact`. El material vivo del tester nunca queda en claro en el log.
  LÍMITE CONOCIDO: `redactor` caza secretos con marca (Bearer/Cookie/JWT/patrones del operador); un token
  OPACO suelto en un cuerpo JSON (`{"session":"…"}`) puede quedar en el transcript — por eso vive en la
  zona E3 (gitignored) y se redacta de nuevo antes del informe. No lo saques de la zona en claro.
- **Loopback + tamaños acotados.** Bind 127.0.0.1 por defecto; cuerpos capados; timeouts en upstream.

Uso (en el anillo efímero, mejora C):
    python tools/http_proxy.py                       # escucha 127.0.0.1:8080, scope de contracts/scope.json
    python tools/http_proxy.py --port 8081 --engagement ACME-2026-001
Config de herramientas/navegador: HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:8080
"""
import argparse
import http.client
import json
import os
import select
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")

sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from acquire_session import in_scope  # noqa: E402  (scope enforcement: import DURO, fail-closed)
from scope_guard import load_scope  # noqa: E402
import redactor  # noqa: E402

BODY_CAP = 8192            # bytes de cuerpo que se REGISTRAN en el transcript (el resto se trunca)
MAX_BODY = 64 * 1024 * 1024  # tope DURO del cuerpo que se lee en memoria (anti-DoS); por encima → 413
_SENSITIVE_HDR = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key",
                  "x-auth-token", "authentication"}
# Hop-by-hop: no se reenvían al upstream ni al cliente (incl. proxy-authorization, que es NUESTRA).
_HOP_HDR = {"proxy-connection", "connection", "keep-alive", "transfer-encoding", "te", "trailer",
            "upgrade", "proxy-authenticate", "proxy-authorization"}
# Al RE-EMITIR la respuesta al cliente: además de las hop-by-hop, NO reenviamos las que ya pone
# send_response()/nuestra recalculada (evita cabeceras DUPLICADAS y el conflicto de Content-Length en HEAD).
_SKIP_RESP = _HOP_HDR | {"content-length", "server", "date"}


def redact_headers(items):
    """Redacta cabeceras para el transcript: las sensibles enteras, el resto por `redactor.redact`."""
    out = {}
    for k, v in items:
        out[k] = "[REDACTED]" if k.lower() in _SENSITIVE_HDR else redactor.redact(v or "")
    return out


def body_preview(raw):
    """Vista NO sensible del cuerpo: truncado a BODY_CAP, redactado; binario → marcador con longitud."""
    if not raw:
        return ""
    truncated = len(raw) > BODY_CAP
    chunk = raw[:BODY_CAP]
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return f"[binary {len(raw)} bytes]"
    text = redactor.redact(text)
    return text + (f"…[+{len(raw) - BODY_CAP} bytes]" if truncated else "")


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # El servidor inyecta: server._scope, server._transcript, server._lock

    def log_message(self, *a):  # silencia el logging por stderr por defecto
        pass

    def _record(self, entry):
        entry.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        line = json.dumps(entry, ensure_ascii=False)
        with self.server._lock:
            with open(self.server._transcript, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _deny(self, what):
        self._record({"event": "blocked", "method": self.command, "target": what, "reason": "out-of-scope"})
        self.send_error(403, "out of scope")

    def do_CONNECT(self):
        host, _, port = self.path.partition(":")
        try:
            port = int(port or "443")
        except ValueError:
            self.send_error(400, "bad CONNECT target")
            return
        if not in_scope(f"https://{host}", self.server._scope):
            self._deny(f"CONNECT {self.path}")
            return
        self._record({"event": "connect", "host": host, "port": port})
        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError as e:
            self.send_error(502, f"bad gateway: {e}")
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        self._tunnel(self.connection, upstream)

    def _tunnel(self, c1, c2):
        """Relay ciego bidireccional (TLS passthrough) hasta que un lado cierre o timeout."""
        try:
            while True:
                r, _, x = select.select([c1, c2], [], [c1, c2], 30)
                if x or not r:
                    break
                for s in r:
                    other = c2 if s is c1 else c1
                    try:
                        data = s.recv(65536)
                    except OSError:
                        return
                    if not data:
                        return
                    try:
                        other.sendall(data)
                    except OSError:
                        return
        finally:
            try:
                c2.close()
            except OSError:
                pass

    def _forward(self):
        url = self.path  # las requests de proxy vienen en forma ABSOLUTA (http://host/…)
        if not url.startswith(("http://", "https://")):
            self.send_error(400, "el proxy espera una URI absoluta")
            return
        # Valida y conecta usando EXACTAMENTE el host de urlsplit (el que se usará para conectar): así el
        # host validado por scope y el host de conexión COINCIDEN (cierra el bypass userinfo user:pass@).
        parts = urlsplit(url)
        try:
            host, port = parts.hostname, parts.port  # .port lanza ValueError si el puerto es inválido
        except ValueError:
            self.send_error(400, "URL con puerto inválido")
            return
        if not host or not in_scope(f"{parts.scheme}://{host}", self.server._scope):
            self._deny(f"{self.command} {url}")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.send_error(400, "Content-Length inválido")
            return
        if length < 0 or length > MAX_BODY:
            self.send_error(413, "cuerpo demasiado grande o Content-Length inválido")
            return
        body = self.rfile.read(length) if length else b""
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in _HOP_HDR}
        conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        conn = None
        try:
            conn = conn_cls(host, port, timeout=15)
            conn.request(self.command, path, body=body, headers=hdrs)
            resp = conn.getresponse()
            resp_body = resp.read()
        except (OSError, http.client.HTTPException) as e:  # upstream caído o HTTP malformado → 502 limpio
            self.send_error(502, f"bad gateway: {e}")
            return
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._record({
            "event": "request", "method": self.command, "url": url,
            "req_headers": redact_headers(self.headers.items()), "req_body": body_preview(body),
            "status": resp.status, "resp_headers": redact_headers(resp.getheaders()),
            "resp_body": body_preview(resp_body),
        })
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in _SKIP_RESP:  # no dupliques Content-Length/Server/Date ni hop-by-hop
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp_body)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _forward


def make_server(scope, transcript, host="127.0.0.1", port=8080):
    """Crea el ThreadingHTTPServer del proxy (loopback). `scope` es el dict de scope.json (fail-closed si
    None) y `transcript` la ruta del JSONL de tráfico. No arranca serve_forever (lo hace el llamador)."""
    if not scope:
        raise ValueError("sin scope.json no se arranca el proxy (fail-closed)")
    httpd = ThreadingHTTPServer((host, port), ProxyHandler)
    httpd._scope = scope
    httpd._transcript = transcript
    httpd._lock = threading.Lock()
    return httpd


def _engagement_id():
    if os.path.isfile(ENGAGEMENT):
        try:
            with open(ENGAGEMENT, encoding="utf-8") as f:
                return json.load(f).get("engagement_id") or "engagement"
        except Exception:  # noqa: BLE001
            pass
    return "engagement"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Proxy HTTP con enforcement de scope + logging (anillo C).",
                                 allow_abbrev=False)
    ap.add_argument("--host", default="127.0.0.1", help="interfaz de escucha (def.: loopback).")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--engagement", default=None, help="engagement_id (def.: el del blackboard).")
    ap.add_argument("--allow-nonloopback", action="store_true",
                    help="permite escuchar fuera de loopback (EXPONE el proxy; úsalo solo si sabes lo que haces).")
    args = ap.parse_args(argv)

    if args.host not in ("127.0.0.1", "::1", "localhost") and not args.allow_nonloopback:
        print(f"http_proxy: --host {args.host} NO es loopback. Un proxy expuesto es superficie de pivote "
              "hacia el lab y su transcript es material E3. Reejecuta con --allow-nonloopback si es "
              "deliberado (y solo dentro del anillo).", file=sys.stderr)
        return 2

    scope = load_scope() if load_scope else None
    if not scope:
        print("http_proxy: no se pudo cargar scope.json — no se arranca (fail-closed)", file=sys.stderr)
        return 2
    eid = args.engagement or _engagement_id()
    ev_dir = os.path.join(ROOT, "engagements", eid, "exploit")
    os.makedirs(ev_dir, exist_ok=True)
    transcript = os.path.join(ev_dir, f"proxy-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.jsonl")
    rel = os.path.relpath(transcript, ROOT).replace("\\", "/")

    try:
        httpd = make_server(scope, transcript, args.host, args.port)
    except (ValueError, OSError) as e:
        print(f"http_proxy: {e}", file=sys.stderr)
        return 2
    print(f"http_proxy escuchando en {args.host}:{args.port} (scope enforced) — transcript: {rel}")
    print("Configura HTTP_PROXY/HTTPS_PROXY=http://%s:%d en la herramienta/navegador del anillo."
          % (args.host, args.port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nhttp_proxy: detenido.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
