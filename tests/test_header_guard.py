#!/usr/bin/env python3
"""
test_header_guard.py — Pruebas del gate de cabecera HTTP obligatoria (header_guard.py).

Cubre la lógica PURA (`header_gate`) sin stdin ni red: qué comandos deben BLOQUEARSE por no llevar la
cabecera que exige el programa (p.ej. Bugcrowd `BUGCROWD: <handle>`) EN UN FLAG DE CABECERA real, y cuáles
pasan. Incluye los evasores/roturas que destapó el council (v2.48.0): la cabecera debe ir en ‑H/‑‑header
(no cuela por URL/body/user-agent/comentario), continuación de línea `\\`, exención por proxy, herramientas
ejecutadas como script, y lista ampliada. Invariante: fail-closed para herramientas HTTP conocidas; pasivas
(subfinder/gau), port-scan (nmap) y mantenimiento (‑version) NO se bloquean; sin `required_http_header` no-op.

Ejecuta:  python tests/test_header_guard.py   (sale 1 si algo falla).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))

import header_guard  # noqa: E402

PASS, FAIL = 0, 0
HDR = "BUGCROWD: c4rm3na"


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


def allowed(cmd, header=HDR):
    return header_guard.header_gate(cmd, header) is None


def blocked(cmd, header=HDR):
    return header_guard.header_gate(cmd, header) is not None


# --- No-op cuando el programa no exige cabecera -------------------------------------------
ok(header_guard.header_gate("curl https://gateway.optus.com.au/api", "") is None,
   "sin required_http_header -> no-op")
ok(header_guard.header_gate("curl https://x.optus.com.au", None) is None, "required None -> no-op")

# --- Cabecera en flag de cabecera real: PASA ---------------------------------------------
ok(allowed('curl -H "BUGCROWD: c4rm3na" https://gateway.optus.com.au/api/ai-search'), "curl -H pasa")
ok(allowed('httpx -H "BUGCROWD: c4rm3na" -u https://webmail.optusnet.com.au/'), "httpx -H pasa")
ok(allowed('ffuf -H "BUGCROWD: c4rm3na" -u https://www.optus.com.au/FUZZ -w wl.txt'), "ffuf -H pasa")
ok(allowed('nuclei -header "BUGCROWD: c4rm3na" -u https://oes.optusnet.com.au/'), "nuclei -header pasa")
ok(allowed('sqlmap --header="BUGCROWD: c4rm3na" -u "https://www.optus.com.au/x?id=1"'),
   "sqlmap --header= pasa")
ok(allowed('wget --header="BUGCROWD: c4rm3na" https://www.optus.com.au/'), "wget --header= pasa")

# --- Normalización: sin espacio y case-insensitive ---------------------------------------
ok(allowed("httpx -H 'BUGCROWD:c4rm3na' -u https://www.optus.com.au/"), "cabecera sin espacio pasa")
ok(allowed('curl -H "bugcrowd: c4rm3na" https://www.optus.com.au/'), "cabecera minúsculas pasa")

# --- [council] La cabecera SOLO cuenta si va en un flag de cabecera: BLOQUEA --------------
ok(blocked('curl "https://www.optus.com.au/?x=BUGCROWD:c4rm3na"'),
   "cabecera en la URL NO cuenta (se bloquea)")
ok(blocked('curl -d "BUGCROWD: c4rm3na" https://www.optus.com.au/'),
   "cabecera en el body -d NO cuenta")
ok(blocked('curl -A "BUGCROWD: c4rm3na" https://www.optus.com.au/'),
   "cabecera en el user-agent -A NO cuenta")
ok(blocked('curl https://www.optus.com.au/ # BUGCROWD: c4rm3na'),
   "cabecera en un comentario NO cuenta")
ok(blocked('curl -o "BUGCROWD: c4rm3na.txt" https://www.optus.com.au/'),
   "cabecera en un nombre de fichero NO cuenta")

# --- Herramientas HTTP sin cabecera: BLOQUEA ----------------------------------------------
ok(blocked("curl https://gateway.optus.com.au/api/ai-search"), "curl sin cabecera se bloquea")
ok(blocked("httpx -l urls.txt -sc"), "httpx -l (lista) sin cabecera se bloquea")
ok(blocked('ffuf -u https://www.optus.com.au/FUZZ -w wl.txt'), "ffuf sin cabecera se bloquea")
ok(blocked('curl -H "BUGCROWD: otrousuario" https://www.optus.com.au/'), "handle equivocado se bloquea")

# --- [council] Herramienta ejecutada como script ------------------------------------------
ok(blocked("python3 sqlmap.py -u https://www.optus.com.au/x?id=1 --batch"),
   "python3 sqlmap.py sin cabecera se bloquea")
ok(allowed('python3 sqlmap.py --header="BUGCROWD: c4rm3na" -u https://www.optus.com.au/'),
   "python3 sqlmap.py con --header= pasa")

# --- [council] Lista ampliada (solo-proxy sin -H) -----------------------------------------
ok(blocked("nikto -host https://www.optus.com.au/"), "nikto directo sin proxy se bloquea")
ok(blocked("whatweb https://www.optus.com.au/"), "whatweb directo se bloquea")

# --- [council] Continuación de línea `\\`+salto: PASA (no falso positivo) -----------------
ok(allowed('curl https://www.optus.com.au/ \\\n  -H "BUGCROWD: c4rm3na"'),
   "continuación de línea con -H en la 2ª línea pasa")

# --- [council] Exención por proxy explícito (operador inyecta la cabecera) ----------------
ok(allowed("curl -x 127.0.0.1:8080 https://www.optus.com.au/"), "curl -x proxy exento")
ok(allowed("proxychains4 nikto -host https://www.optus.com.au/"), "proxychains nikto exento")

# --- Pipelines y separadores --------------------------------------------------------------
ok(blocked('subfinder -d optus.com.au -silent | httpx -sc'), "pipe subfinder|httpx sin cabecera bloquea")
ok(allowed('subfinder -d optus.com.au -silent | httpx -H "BUGCROWD: c4rm3na" -sc'),
   "pipe subfinder|httpx con -H pasa")
ok(blocked('curl https://a.optus.com.au & curl -H "BUGCROWD: c4rm3na" https://b.optus.com.au'),
   "separador & : el primer curl sin cabecera bloquea")

# --- No HTTP / pasivas / mantenimiento: PASA ----------------------------------------------
ok(allowed("nmap -p80,443 -sV www.optus.com.au"), "nmap no exige cabecera")
ok(allowed("subfinder -d optus.com.au -silent"), "subfinder pasivo no exige cabecera")
ok(allowed("gau optus.com.au"), "gau pasivo no exige cabecera")
ok(allowed("nuclei -update-templates"), "nuclei -update-templates exento")
ok(allowed("curl --version"), "curl --version exento")
ok(allowed("cat contracts/scope.json"), "comando no ofensivo pasa")
ok(allowed('echo "corre curl mas tarde"'), "mención de curl en un string no dispara")

# --- El motivo de bloqueo NO ecoa el comando (no filtra secretos) ------------------------
reason = header_guard.header_gate('curl -H "Authorization: Bearer SECRETO123" https://www.optus.com.au/', HDR)
ok(reason is not None and "SECRETO123" not in reason and "Bearer" not in reason,
   "el motivo de bloqueo no filtra el token del comando")


print(f"\n  RESUMEN test_header_guard:  {PASS} OK   {FAIL} fallos\n")
sys.exit(1 if FAIL else 0)
