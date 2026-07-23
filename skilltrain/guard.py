#!/usr/bin/env python3
"""guard.py — lint de GOBERNANZA determinista de una skill candidata (SkillOpt).

El optimizer propone ediciones de texto de una skill. Antes de puntuar un candidato, este lint lo RECHAZA si
intenta relajar el suelo de seguridad o meter datos de cliente. Es una barrera determinista (como
`memory_guard`/`secret_scan` del motor), no un juicio del modelo: el reward jamás debe premiar "menos
safeguards" (evasión OBLITERATUS rechazada), y una skill es TÉCNICA GENERALIZADA (zona E3, sin datos de
cliente). Filosofía: fail-closed — ante la duda, rechaza.

Uso:  python skilltrain/guard.py plugin/skills/web-app-security/SKILL.md
"""
import re
import sys

# PRECISO a propósito: una skill de metodología discute scope/bypass/access-control legítimamente ("no
# salgas del scope", "WAF bypass", "authentication bypass"), así que NO se puede flaggear vocabulario
# genérico (daría falsos positivos y descartaría skills buenas). Solo se rechaza lo INEQUÍVOCO: tocar los
# guards del MOTOR por su NOMBRE, los flags que apagan el gate, o poner la aprobación en auto. Case-insensitive.
_ENGINE_GUARDS = (r"scope_guard|approval_gate|budget_guard|memory_guard|secret_scan|noise_guard|loop_guard|"
                  r"circuit_breaker|fs_guard|a2a_guard|blackboard_guard|steering_nudge|a2a_router_nudge")
_FORBIDDEN = [
    (r"--dangerously-skip-permissions", "invoca el bypass de permisos del harness"),
    (r"--yolo\b", "flag --yolo (apaga scope_guard en run_gate)"),
    (r"\b(disable|desactiv\w+|bypass|elud\w+|salt\w+|apag\w+|deshabilit\w+|off)\b[^.\n]{0,40}\b(" + _ENGINE_GUARDS + r")\b",
     "propone desactivar/eludir un guard NOMBRADO del motor"),
    (r"\b(" + _ENGINE_GUARDS + r")\b[^.\n]{0,40}\b(disable|off|skip|bypass|desactiv\w+|elud\w+|apag\w+|deshabilit\w+)\b",
     "propone desactivar un guard NOMBRADO del motor"),
    (r"approval_mode\s*[:=]?\s*[\"']?auto", "fuerza approval_mode=auto (sin supervisión)"),
    (r"\bORCH_APPROVAL_MODE\b[^.\n]{0,15}auto", "fuerza ORCH_APPROVAL_MODE=auto (sin supervisión)"),
]

# Señales de datos de cliente incrustados (una skill es genérica; no debe traer un target/secreto concreto).
_CLIENT_DATA = [
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP concreta incrustada (¿dato de cliente?)"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key incrustada"),
    (r"\beyJ[A-Za-z0-9_-]{20,}\b", "JWT incrustado"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "clave privada incrustada"),
]


def lint_skill(text):
    """Devuelve lista de violaciones (str). Vacía = candidato admisible."""
    out = []
    for rx, why in _FORBIDDEN:
        m = re.search(rx, text, re.I)
        if m:
            out.append(f"[gobernanza] {why}: …{m.group(0)[:60]}…")
    for rx, why in _CLIENT_DATA:
        m = re.search(rx, text)
        if m:
            out.append(f"[datos-cliente] {why}: …{m.group(0)[:40]}…")
    return out


def assert_skill_safe(text):
    """Lanza ValueError con TODAS las violaciones si el candidato no es admisible."""
    v = lint_skill(text)
    if v:
        raise ValueError("skill candidata RECHAZADA por gobernanza:\n  - " + "\n  - ".join(v))


def main():
    if len(sys.argv) != 2:
        print("uso: python skilltrain/guard.py <ruta-SKILL.md>", file=sys.stderr)
        sys.exit(2)
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    v = lint_skill(text)
    if v:
        print("RECHAZADA:\n  - " + "\n  - ".join(v), file=sys.stderr)
        sys.exit(1)
    print("OK: candidata admisible (gobernanza).")


if __name__ == "__main__":
    main()
