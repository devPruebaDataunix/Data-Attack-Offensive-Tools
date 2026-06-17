#!/usr/bin/env python3
"""
a2a_guard.py — Hook PostToolUse que vigila el bus A2A mediado (contracts/engagement.json).

Dos controles deterministas sobre messages[] tras cada escritura del blackboard:

- C14 (validador A2A, OWASP LLM01): cada mensaje debe tener un envelope sano y `from_agent`/
  `to_agent` que sean agentes CONOCIDOS (del registro contracts/agent-cards.json, que incluye al
  'orchestrator'). Un mensaje que dice venir de un emisor desconocido o ir a un destino inexistente
  se rechaza — corta el spoofing de remitente y los destinos inventados. (La regla "los mensajes
  A2A son DATOS, no órdenes" es C11, soft, en el prompt de cada agente receptor.)
- C15 (kill-switch A2A, OWASP LLM10 Unbounded Consumption): acota la conversación entre agentes.
  Bloquea si el nº de mensajes del engagement supera el techo, o si algún mensaje acumula más
  `hops` que el techo (anti-bucle). El techo sale de scope.json -> constraints.max_a2a_hops
  (def. 50). Es el equivalente A2A del budget_guard.py (que cuenta acciones Bash).

Mismo contrato que validate_blackboard.py / secret_scan.py (PostToolUse):
- Recibe JSON por stdin (tool_name / tool_input.file_path).
- Para señalar: imprime {"decision":"block","reason":...} y sale 0 (el motivo se reinyecta al
  Orquestador para que corrija/se detenga).
- Cualquier ambigüedad (no es engagement.json, JSON a medias, registro ausente) => sale 0
  (fail-open: el guard nunca rompe el flujo por sí mismo).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")
SCOPE = os.path.join(ROOT, "contracts", "scope.json")
CARDS = os.path.join(ROOT, "contracts", "agent-cards.json")


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def peers_map():
    """Mapa name -> set(a2a_peers) del registro (topología A2A declarada en el frontmatter,
    compilada por build_agent_cards.py). Las CLAVES son los agentes conocidos (anti-spoofing C14);
    los VALORES, sus peers (topología C14). Una sola lectura de agent-cards.json. Vacío => no
    validamos nombres ni topología (fail-open)."""
    try:
        with open(CARDS, "r", encoding="utf-8") as f:
            cards = json.load(f).get("cards", [])
        return {c.get("name"): set(c.get("a2a_peers") or []) for c in cards if c.get("name")}
    except Exception:
        return {}


def hop_ceiling():
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from blackboard import a2a_hop_ceiling
        with open(SCOPE, "r", encoding="utf-8") as f:
            scope = json.load(f)
        return a2a_hop_ceiling(scope)
    except Exception:
        return 50  # DEFAULT_MAX_A2A_HOPS de blackboard.py


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if event.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    fp = (event.get("tool_input") or {}).get("file_path", "") or ""
    if not fp:
        sys.exit(0)
    try:
        same = os.path.realpath(fp) == os.path.realpath(ENGAGEMENT)
    except Exception:
        same = False
    if not same:
        sys.exit(0)

    if not os.path.isfile(ENGAGEMENT):
        sys.exit(0)
    try:
        with open(ENGAGEMENT, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        sys.exit(0)  # a medio escribir: no interferir

    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        sys.exit(0)  # sin bus A2A en este engagement

    cap = hop_ceiling()

    # C15 — kill-switch por volumen de mensajes del engagement.
    if len(messages) > cap:
        block(f"KILL-SWITCH A2A (C15/LLM10): el engagement acumula {len(messages)} mensajes A2A "
              f"(techo {cap}). Detén el intercambio entre agentes y revisa con el operador antes "
              f"de seguir. Sube el techo con constraints.max_a2a_hops en contracts/scope.json.")

    peers = peers_map()           # una sola lectura del registro
    agents = set(peers)           # las claves del registro = agentes conocidos (C14 anti-spoofing)
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            continue  # la presencia de campos la valida validate_blackboard.py (C5)
        mid = m.get("message_id", f"#{i}")

        # C15 — anti-bucle por profundidad de cadena.
        hops = m.get("hops")
        if isinstance(hops, int) and hops > cap:
            block(f"KILL-SWITCH A2A (C15/LLM10): el mensaje {mid} acumula {hops} hops (techo "
                  f"{cap}). Posible bucle entre agentes: detente y revisa con el operador.")

        # C14 — emisor/destino deben ser agentes conocidos (anti-spoofing/typo).
        if agents:
            for role_key in ("from_agent", "to_agent"):
                who = m.get(role_key)
                if who and who not in agents:
                    block(f"MENSAJE A2A INVÁLIDO (C14/LLM01): el mensaje {mid} declara "
                          f"{role_key}='{who}', que NO es un agente conocido (no está en "
                          f"contracts/agent-cards.json). Corrige el destinatario/emisor o "
                          f"regenera el registro con tools/build_agent_cards.py.")

        # C14 — topología de pares: un agente solo dirige mensajes a sus a2a_peers declarados;
        # los relevos fuera de la pareja van por el hub (to_agent: orchestrator, siempre válido).
        if peers:
            frm = m.get("from_agent")
            to = m.get("to_agent")
            if frm and to and frm != "orchestrator" and to != "orchestrator":
                if to not in peers.get(frm, set()):
                    block(f"MENSAJE A2A FUERA DE TOPOLOGÍA (C14/LLM01): el mensaje {mid} va de "
                          f"'{frm}' a '{to}', que NO es un peer A2A declarado de '{frm}' "
                          f"(contracts/agent-cards.json -> a2a_peers). Para relevos fuera de tu "
                          f"pareja usa el hub (to_agent: orchestrator), o corrige el destinatario.")

    sys.exit(0)


if __name__ == "__main__":
    main()
