#!/usr/bin/env python3
"""
blackboard_guard.py — Hook PreToolUse (Bash) que impide ESCRIBIR el blackboard
(`contracts/engagement.json`) por la vía de Bash, forzando que toda mutación pase por las tools
`Write`/`Edit` — que SÍ están gateadas por `validate_blackboard`/`secret_scan`/`a2a_guard` (PostToolUse
sobre Write|Edit|MultiEdit). Cierra el hueco que señalaron los councils de las mejoras A y D: un agente
con `Bash` (p.ej. `auth-recon`, que maneja material de sesión VIVO) podría volcar un secreto al
blackboard con `echo … > engagement.json` / `sed -i` / `python -c "open(...,'w')"` **esquivando** los
guards de secreto. Este guard lo bloquea de forma determinista.

Cobertura (contrato CONSCIENTE, no un sandbox completo): caza los patrones de escritura COMUNES que
nombran el blackboard —redirección `>`/`>>`, `tee`, `sed -i`, `cp`/`mv`/`dd`/`install`/`truncate`,
`open(...,'w'/'a')`, `Path(...).write_text/write_bytes` y `shutil.copy*/move` de Python—. Un agente
decidido podría ofuscar (base64, variable con la ruta): el confinamiento DURO es el contenedor efímero
(mejora C) + que las tools nunca emiten material a stdout.
LEER el blackboard (cat/jq/grep/python-read) NO se bloquea. Fail-open ante ambigüedad.

Protocolo Claude Code (igual que scope_guard.py): stdin JSON {tool_name, tool_input.command}; para
BLOQUEAR imprime la decisión PreToolUse (permissionDecision=deny) y sale 0; ambigüedad => sale 0.

Solo stdlib.
"""
import json
import re
import sys

# El nombre del blackboard (con o sin el prefijo contracts/, `/` o `\`).
_BB = r"(?:contracts[\\/])?engagement\.json"

# Patrones de ESCRITURA que nombran el blackboard. Cada uno describe una vía de mutación por Bash.
_WRITE_PATTERNS = [
    (re.compile(r">>?\s*[\"']?[^\s|;&>\"']*" + _BB, re.I), "redirección > / >> al blackboard"),
    (re.compile(r"\btee\b[^|;&]*" + _BB, re.I), "tee sobre el blackboard"),
    (re.compile(r"\bsed\b[^|;&]*-i[^|;&]*" + _BB, re.I), "sed -i (edición in-place) del blackboard"),
    (re.compile(r"\b(?:cp|mv|dd|install|rsync|truncate)\b[^|;&]*" + _BB, re.I), "cp/mv/dd/install/truncate al blackboard"),
    (re.compile(r"open\s*\([^)]*" + _BB + r"[^)]*,\s*[\"'][wa]", re.I), "open(..., 'w'/'a') de Python sobre el blackboard"),
    (re.compile(r"\.write\s*\([^)]*\)[^;]*" + _BB, re.I), ".write() de Python sobre el blackboard"),
    # `Path("…engagement.json").write_text/bytes(…)` — la ruta va ANTES del método (el arg es el
    # contenido). NO casamos el blackboard DENTRO de los args de write_* (ahí sería contenido/lectura).
    (re.compile(r"[\"'][^\"']*" + _BB + r"[\"']\s*\)?\s*\.write_(?:text|bytes)", re.I), "Path('…engagement.json').write_text/bytes"),
    (re.compile(r"shutil\.(?:copy\w*|move)\s*\([^)]*" + _BB, re.I), "shutil.copy*/move al blackboard"),
]


def blocking_reason(command):
    """Motivo (str) si `command` escribe el blackboard por Bash, o None. Función pura y testeable."""
    if not command or "engagement.json" not in command:
        return None
    for rx, label in _WRITE_PATTERNS:
        if rx.search(command):
            return label
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)
    if event.get("tool_name") != "Bash":
        sys.exit(0)
    command = (event.get("tool_input") or {}).get("command", "") or ""
    label = blocking_reason(command)
    if label:
        reason = (
            f"blackboard_guard: BLOQUEADA una escritura del blackboard por Bash ({label}). El blackboard "
            "`contracts/engagement.json` SOLO se muta con las tools `Write`/`Edit` — que pasan por "
            "`validate_blackboard`/`secret_scan`/`a2a_guard`. Escribirlo por Bash esquivaría esos guards "
            "de secreto/esquema. Usa Write/Edit para actualizar el blackboard. (Leerlo con cat/jq está bien.)"
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
