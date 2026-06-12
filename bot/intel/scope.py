"""
Pre-chequeo de alcance para el canal Telegram.

NO sustituye al hook determinista scope_guard.py (que bloquea cada acción fuera de
scope en tiempo de ejecución). Aquí solo decidimos si hay que PREGUNTAR al operador
antes de lanzar al Orquestador — para cumplir "si falta scope, pregunta; no adivines"
(AGENTS.md, Regla 0).
"""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Optional

_DOMAIN = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.I)
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL = re.compile(r"https?://[^\s/]+", re.I)


def load_scope(repo) -> Optional[dict]:
    f = Path(repo) / "contracts" / "scope.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _empty(scope: Optional[dict]) -> bool:
    if not scope:
        return True
    ins = scope.get("in_scope") or {}
    return not any(ins.get(k) for k in ("domains", "ips", "cidrs", "urls"))


def extract_targets(text: str) -> dict:
    text = text or ""
    urls = set(_URL.findall(text))
    hosts = set()
    for u in urls:
        host = re.sub(r"^https?://", "", u, flags=re.I).split("/")[0].split(":")[0]
        hosts.add(host.lower())
    ips = set(_IP.findall(text))
    domains = {d.lower() for d in _DOMAIN.findall(text)} | hosts
    domains = {d for d in domains if not _IP.fullmatch(d)}
    return {"domains": domains, "ips": ips, "urls": urls}


def _host_in_scope(host: str, scope: dict) -> bool:
    host = host.lower().rstrip(".")
    for d in (scope.get("in_scope", {}).get("domains") or []):
        d = d.lower().rstrip(".")
        if d.startswith("*."):
            base = d[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == d:
            return True
    return False


def _ip_in_scope(ip: str, scope: dict) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    ins = scope.get("in_scope", {})
    if ip in (ins.get("ips") or []):
        return True
    for cidr in (ins.get("cidrs") or []):
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def scope_question(task: str, scope: Optional[dict]) -> Optional[str]:
    """Pregunta a devolver al operador si falta/insuficiente el scope; None si todo OK."""
    if _empty(scope):
        return (
            "No tengo alcance definido (`contracts/scope.json` vacío o ausente). "
            "Antes de tocar nada, dime el *scope autorizado*: dominios, IPs/CIDR y/o URLs "
            "del engagement, y el cliente / referencia de autorización."
        )
    tg = extract_targets(task)
    out = [h for h in tg["domains"] if not _host_in_scope(h, scope)]
    out += [ip for ip in tg["ips"] if not _ip_in_scope(ip, scope)]
    if out:
        uniq = ", ".join(sorted(set(out))[:8])
        return (
            f"Esa orden menciona objetivos que *no están en el scope actual*: `{uniq}`.\n"
            "¿Están autorizados? Si sí, confírmalo (y dime si los añado a `scope.json`); "
            "si no, los dejo fuera y sigo solo con lo que está en alcance."
        )
    return None
