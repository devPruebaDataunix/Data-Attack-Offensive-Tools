#!/usr/bin/env python3
"""Tests del PROXY HTTP con enforcement de scope (mejora v2.60 — idea de strix).

Cubre `tools/http_proxy.py`: redacción de cabeceras/cuerpo (E3), fail-closed sin scope, y una integración
LOOPBACK real (target http.server + proxy + cliente) que verifica el reenvío, el transcript y el 403
fuera de scope. Solo abre sockets de loopback (sin red externa).

    python tests/test_http_proxy.py    (sale 1 si algo falla).
"""
import http.client
import json
import os
import tempfile
import threading
import time
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


import http_proxy as hp  # noqa: E402

# ── redacción de cabeceras (E3) ──────────────────────────────────────────────────────
rh = hp.redact_headers([("Authorization", "Bearer abc.def.ghi"), ("Cookie", "session=xyz"),
                        ("User-Agent", "curl/8"), ("X-Api-Key", "k-123")])
check("Authorization redactada entera", rh["Authorization"] == "[REDACTED]")
check("Cookie redactada entera", rh["Cookie"] == "[REDACTED]")
check("X-Api-Key redactada entera", rh["X-Api-Key"] == "[REDACTED]")
check("User-Agent no sensible se conserva", rh["User-Agent"] == "curl/8")

# ── cuerpo: truncado + binario ───────────────────────────────────────────────────────
check("body_preview vacío -> ''", hp.body_preview(b"") == "")
big = b"A" * (hp.BODY_CAP + 500)
prev = hp.body_preview(big)
check("body_preview trunca cuerpos grandes", "…[+500 bytes]" in prev and len(prev) < len(big))
check("body_preview marca binario", hp.body_preview(b"\xff\xfe\x00\x01") == "[binary 4 bytes]")

# ── fail-closed sin scope ────────────────────────────────────────────────────────────
try:
    hp.make_server(None, "x.jsonl")
    check("make_server sin scope -> ValueError (fail-closed)", False)
except ValueError:
    check("make_server sin scope -> ValueError (fail-closed)", True)

# ── integración loopback: target + proxy + cliente ───────────────────────────────────
TARGET_BODY = b"HELLO-TARGET-OK"


class _Target(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(TARGET_BODY)))
        self.end_headers()
        self.wfile.write(TARGET_BODY)


target = ThreadingHTTPServer(("127.0.0.1", 0), _Target)
tport = target.server_address[1]
threading.Thread(target=target.serve_forever, daemon=True).start()

# scope con 127.0.0.1 EN SCOPE (el target es loopback); todo lo demás fuera.
scope = {"in_scope": {"ips": ["127.0.0.1"], "domains": [], "cidrs": []},
         "out_of_scope": {"ips": [], "domains": [], "cidrs": []}}
tf = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
tf.close()
proxy = hp.make_server(scope, tf.name, "127.0.0.1", 0)
pport = proxy.server_address[1]
threading.Thread(target=proxy.serve_forever, daemon=True).start()
time.sleep(0.2)

try:
    # request EN SCOPE a través del proxy (forma absoluta).
    c = http.client.HTTPConnection("127.0.0.1", pport, timeout=10)
    c.request("GET", f"http://127.0.0.1:{tport}/", headers={"Authorization": "Bearer SECRET-TOKEN-XYZ"})
    r = c.getresponse()
    relayed = r.read()
    c.close()
    check("proxy reenvía la respuesta del target EN SCOPE", r.status == 200 and relayed == TARGET_BODY)

    # request FUERA de scope -> 403 (sin tocar red).
    c2 = http.client.HTTPConnection("127.0.0.1", pport, timeout=10)
    c2.request("GET", "http://blocked.example/x")
    r2 = c2.getresponse()
    r2.read()
    c2.close()
    check("host fuera de scope -> 403", r2.status == 403)

    time.sleep(0.1)
    with open(tf.name, encoding="utf-8") as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]
    ev = {e["event"] for e in lines}
    check("transcript registra la request EN SCOPE", "request" in ev)
    check("transcript registra el bloqueo fuera de scope", "blocked" in ev)
    req = next(e for e in lines if e["event"] == "request")
    check("transcript redacta el Authorization del tester (E3)",
          req["req_headers"].get("Authorization") == "[REDACTED]" and "SECRET-TOKEN-XYZ" not in json.dumps(lines))
finally:
    proxy.shutdown(); proxy.server_close()
    target.shutdown(); target.server_close()
    try:
        os.remove(tf.name)
    except OSError:
        pass

# ── integración II: bypass userinfo (BLOQUEANTE seguridad), POST/HEAD, upstream malformado, CL inválido ──
import socket  # noqa: E402


class _Target2(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)  # eco del cuerpo

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "99999")  # anuncia grande, sin cuerpo (HEAD): el proxy debe normalizar
        self.end_headers()


t2 = ThreadingHTTPServer(("127.0.0.1", 0), _Target2)
t2port = t2.server_address[1]
threading.Thread(target=t2.serve_forever, daemon=True).start()

# servidor RAW que responde basura no-HTTP (para probar BadStatusLine -> 502)
bad = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
bad.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
bad.bind(("127.0.0.1", 0))
bad.listen(1)
bad_port = bad.getsockname()[1]


def _bad_loop():
    while True:
        try:
            conn, _ = bad.accept()
        except OSError:
            return
        try:
            conn.recv(4096)
            conn.sendall(b"NOT-HTTP-GARBAGE\r\n\r\n")
            conn.close()
        except OSError:
            pass


threading.Thread(target=_bad_loop, daemon=True).start()

# scope basado en DOMINIO (127.0.0.1 NO está en scope) para el test de bypass userinfo.
scope_dom = {"in_scope": {"domains": ["scope.example"], "ips": [], "cidrs": []},
             "out_of_scope": {"ips": [], "domains": [], "cidrs": []}}
# scope con 127.0.0.1 en scope para POST/HEAD/bad-upstream.
scope_ip = {"in_scope": {"ips": ["127.0.0.1"], "domains": [], "cidrs": []},
            "out_of_scope": {"ips": [], "domains": [], "cidrs": []}}
tf2 = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False); tf2.close()
tf3 = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False); tf3.close()
proxy_dom = hp.make_server(scope_dom, tf2.name, "127.0.0.1", 0)
proxy_ip = hp.make_server(scope_ip, tf3.name, "127.0.0.1", 0)
pdport = proxy_dom.server_address[1]
pipport = proxy_ip.server_address[1]
threading.Thread(target=proxy_dom.serve_forever, daemon=True).start()
threading.Thread(target=proxy_ip.serve_forever, daemon=True).start()
time.sleep(0.2)


def _raw(pport, req):
    """Envía bytes crudos al proxy y devuelve la primera línea de la respuesta."""
    s = socket.create_connection(("127.0.0.1", pport), timeout=10)
    try:
        s.sendall(req)
        data = s.recv(4096)
        return data.split(b"\r\n", 1)[0].decode("latin1")
    finally:
        s.close()


try:
    # BLOQUEANTE: userinfo bypass — host validado (scope.example) != host de conexión (127.0.0.1) -> 403.
    cbp = http.client.HTTPConnection("127.0.0.1", pdport, timeout=10)
    cbp.request("GET", f"http://scope.example:x@127.0.0.1:{t2port}/")
    rbp = cbp.getresponse(); rbp.read(); cbp.close()
    check("BLOQUEANTE cerrado: userinfo user:pass@ no bypassa el scope (-> 403)", rbp.status == 403)

    # POST con cuerpo: el target lo recibe entero (eco).
    cp = http.client.HTTPConnection("127.0.0.1", pipport, timeout=10)
    cp.request("POST", f"http://127.0.0.1:{t2port}/", body=b"BODY-1234567890")
    rp = cp.getresponse(); echoed = rp.read(); cp.close()
    check("POST reenvía el cuerpo completo al target", rp.status == 200 and echoed == b"BODY-1234567890")

    # HEAD: el proxy normaliza a UN solo Content-Length (=0), no el 99999 del upstream.
    ch = http.client.HTTPConnection("127.0.0.1", pipport, timeout=10)
    ch.request("HEAD", f"http://127.0.0.1:{t2port}/")
    rh = ch.getresponse(); rh.read()
    cl = rh.getheader("Content-Length")
    ch.close()
    check("HEAD -> un único Content-Length correcto (0), sin duplicado/conflicto", cl == "0")

    # upstream malformado (no-HTTP) -> 502 limpio, no corte de conexión.
    cb = http.client.HTTPConnection("127.0.0.1", pipport, timeout=10)
    cb.request("GET", f"http://127.0.0.1:{bad_port}/")
    rb = cb.getresponse(); rb.read(); cb.close()
    check("upstream malformado -> 502 (no cae el handler)", rb.status == 502)

    # Content-Length no numérico en la request -> 400 (no crash).
    line = _raw(pipport, f"POST http://127.0.0.1:{t2port}/ HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n".encode())
    check("Content-Length inválido -> 400", "400" in line)
finally:
    for p in (proxy_dom, proxy_ip):
        p.shutdown(); p.server_close()
    t2.shutdown(); t2.server_close()
    bad.close()
    for tt in (tf2.name, tf3.name):
        try:
            os.remove(tt)
        except OSError:
            pass

print()
if _fail:
    print(f"FALLOS: {len(_fail)} -> {_fail}")
    sys.exit(1)
print("TODOS OK")
