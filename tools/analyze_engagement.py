#!/usr/bin/env python3
"""
analyze_engagement.py — Auditoría de COHERENCIA de extremo a extremo del engagement.

Adaptación del `/analyze` de spec-driven development (GitHub Spec Kit) al dominio ofensivo:
cruza CONSTITUTION.md ↔ scope.json ↔ engagement.json ↔ findings ↔ informe y reporta
incongruencias ANTES de cerrar. NO ejecuta nada ofensivo; solo lee artefactos.

Comprueba, entre otros:
  - targets del blackboard fuera de scope (y `in_scope` incoherente con scope.json);
  - findings `confirmed`/`exploited` sin `evidence` (viola "evidencia o no existe");
  - findings sin fuente (`source_refs`/`cve`) — "sin fuente no se explota";
  - autorización caducada; `target_id` rotos; `cvss`/severidad inválidos.

    python tools/analyze_engagement.py
    python tools/analyze_engagement.py --scope contracts/scope.json --engagement contracts/engagement.json

Sale con código !=0 si hay FALLOS (no solo avisos). Solo stdlib.
"""
from __future__ import annotations

import argparse
import glob
import ipaddress
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Consolas Windows (cp1252) no codifican los caracteres de caja/acentos: forzamos utf-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

URL_RE = re.compile(r"https?://([^/\s:]+)", re.I)
IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
SEVERITIES = {"info", "low", "medium", "high", "critical"}
REPORTABLE = {"confirmed", "exploited"}


# ── matching de alcance (ESPEJO de .claude/hooks/scope_guard.py) ────────────────
def domain_in_list(host, patterns):
    host = (host or "").lower().rstrip(".")
    for p in patterns:
        p = (p or "").lower().rstrip(".")
        if p.startswith("*."):
            base = p[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == p:
            return True
    return False


def ip_in_scope(ip, ips, cidrs):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if ip in ips:
        return True
    for c in cidrs:
        try:
            if addr in ipaddress.ip_network(c, strict=False):
                return True
        except ValueError:
            continue
    return False


def _host_of(asset):
    """Extrae el host de un asset (URL -> host; si no, el propio asset)."""
    asset = (asset or "").strip()
    m = URL_RE.match(asset)
    return m.group(1) if m else asset


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def main():
    ap = argparse.ArgumentParser(description="Auditoría de coherencia del engagement.")
    ap.add_argument("--scope", default=os.path.join(ROOT, "contracts", "scope.json"))
    ap.add_argument("--engagement", default=os.path.join(ROOT, "contracts", "engagement.json"))
    args = ap.parse_args()

    ok, warn, fail = [], [], []
    def OK(m):   ok.append(m);   print(f"  [OK]    {m}")
    def WARN(m): warn.append(m); print(f"  [AVISO] {m}")
    def FAIL(m): fail.append(m); print(f"  [FALLO] {m}")

    print("── Auditoría de coherencia del engagement ──")

    # 1) Constitución
    const = os.path.join(ROOT, "CONSTITUTION.md")
    if os.path.isfile(const):
        txt = open(const, encoding="utf-8").read()
        mv = re.search(r"Versi[oó]n\s+([0-9]+\.[0-9]+\.[0-9]+)", txt)
        OK(f"CONSTITUTION.md presente" + (f" (v{mv.group(1)})" if mv else ""))
    else:
        WARN("CONSTITUTION.md ausente — define los principios del engagement (ver docs/engagement-driven.md)")

    # 2) Scope
    scope = _load(args.scope)
    if scope is None:
        FAIL(f"{os.path.relpath(args.scope, ROOT)} ausente o ilegible — sin alcance no se opera (§1)")
        return _summary(ok, warn, fail)
    ins = scope.get("in_scope", {}) or {}
    if not any(ins.get(k) for k in ("domains", "ips", "cidrs", "urls")):
        FAIL("scope.json sin alcance: in_scope vacío")
    else:
        OK("scope.json con alcance definido")

    # listas de matching (igual que scope_guard: dominios + hosts de urls)
    in_domains = list(ins.get("domains", []) or [])
    in_domains += [URL_RE.match(u).group(1) for u in (ins.get("urls", []) or []) if URL_RE.match(u)]
    in_ips = list(ins.get("ips", []) or [])
    in_cidrs = list(ins.get("cidrs", []) or [])
    out = scope.get("out_of_scope", {}) or {}
    out_domains = list(out.get("domains", []) or [])
    out_ips = list(out.get("ips", []) or [])

    # Autorización vigente
    auth = scope.get("authorization", {}) or {}
    vu = auth.get("valid_until")
    if vu:
        try:
            until = date.fromisoformat(str(vu)[:10])
            if until < date.today():
                FAIL(f"autorización CADUCADA el {vu} (§1) — no se opera")
            else:
                OK(f"autorización vigente (hasta {vu})")
        except ValueError:
            WARN(f"authorization.valid_until con formato no ISO: {vu}")

    # 3) Engagement (blackboard)
    eng = _load(args.engagement)
    if eng is None:
        WARN(f"{os.path.relpath(args.engagement, ROOT)} ausente — aún no hay engagement activo que auditar")
        return _summary(ok, warn, fail)

    if not eng.get("scope_ref"):
        WARN("engagement.scope_ref vacío (debería apuntar a scope.json)")

    targets = eng.get("targets", []) or []
    tids = {t.get("target_id") for t in targets if t.get("target_id")}

    out_n = 0
    for t in targets:
        tid = t.get("target_id", "?")
        host = _host_of(t.get("asset", ""))
        if not host:
            WARN(f"target {tid}: sin 'asset'")
            continue
        is_ip = bool(IP_RE.match(host))
        explicit_out = (is_ip and host in out_ips) or (not is_ip and domain_in_list(host, out_domains))
        actual_in = ip_in_scope(host, in_ips, in_cidrs) if is_ip else domain_in_list(host, in_domains)
        if explicit_out or not actual_in:
            FAIL(f"target {tid} ({host}) está FUERA de scope en el blackboard (§1)")
            out_n += 1
        elif t.get("in_scope") is False:
            WARN(f"target {tid} ({host}) marcado in_scope=false pero SÍ está en scope (incoherencia)")
    if targets and out_n == 0:
        OK(f"{len(targets)} targets del blackboard, todos dentro de scope")

    # 4) Findings
    findings = eng.get("findings", []) or []
    bad = 0
    for f in findings:
        fid = f.get("finding_id", "?")
        st = (f.get("status") or "").lower()
        if f.get("target_id") and f["target_id"] not in tids:
            WARN(f"finding {fid}: target_id '{f['target_id']}' no existe en targets[]")
        if st in REPORTABLE and not (f.get("evidence") or "").strip():
            FAIL(f"finding {fid} [{st}] SIN evidence — viola 'evidencia o no existe' (§3)"); bad += 1
        if st in REPORTABLE and not (f.get("source_refs") or f.get("cve") or f.get("exploit_sources")):
            FAIL(f"finding {fid} [{st}] SIN fuente (source_refs/cve) — 'sin fuente no se explota' (§3,§4)"); bad += 1
        sev = (f.get("severity") or "").lower()
        if sev and sev not in SEVERITIES:
            WARN(f"finding {fid}: severidad inválida '{sev}'")
        cvss = f.get("cvss")
        if cvss is not None and not (isinstance(cvss, (int, float)) and 0 <= cvss <= 10):
            WARN(f"finding {fid}: cvss fuera de [0,10]: {cvss}")
    if findings and bad == 0:
        OK(f"{len(findings)} findings, todos con evidencia y fuente donde corresponde")

    # 5) Informe (coherencia blanda)
    reports = sorted(glob.glob(os.path.join(ROOT, "report", "INFORME-*.md")))
    if reports:
        n_rep = sum(1 for f in findings if (f.get("status") or "").lower() in REPORTABLE)
        OK(f"informe presente ({len(reports)}); findings reportables (confirmed/exploited): {n_rep}")

    return _summary(ok, warn, fail)


def _summary(ok, warn, fail):
    print("\n" + "=" * 60)
    print(f"  COHERENCIA:  {len(ok)} OK   {len(warn)} avisos   {len(fail)} fallos")
    print("=" * 60)
    if fail:
        print("  -> Resuelve los FALLOS antes de cerrar/reportar (corrige el artefacto, no el verificador).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
