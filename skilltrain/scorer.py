#!/usr/bin/env python3
"""scorer.py — reward de SkillOpt = pass@k del eval-harness, SIEMPRE con canario.

Es el punto de integración crítico contra el reward-hacking: el optimizer maximizará el reward, así que el
reward DEBE ser inforjable. Por eso el scorer solo puntúa evals **canary-capable** (bloque `canary` en
single-host, o `canary.per_host` en multi_host) y siempre lanza `run_gate --canary` — la prueba es un token
aleatorio plantado en el target (v2.63/v2.64), no una constante que el modelo ya conoce. Un eval sin canario
se RECHAZA (no se degrada a una señal forjable).

El LANZAMIENTO real (run_gate → `claude -p`/opencode contra un lab) es del OPERADOR en Kali; aquí el scorer
recibe un `runner` inyectable `runner(ev) -> bool` (True=PASS). `shell_runner` es el runner de producción
(Kali); los tests inyectan uno falso para verificar la lógica de gate/pass@k sin lanzar nada.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guard  # noqa: E402  (skilltrain/guard.py)
from apply_skill import SkillSwap, DEFAULT_SKILLS_ROOT  # noqa: E402


def eval_is_canary_capable(ev):
    """True si el eval permite graduar con canario inforjable: `canary.plant` (single-host) o
    `canary.per_host` no vacío (multi_host). Solo estos evals dan una señal de recompensa válida."""
    c = ev.get("canary")
    if not isinstance(c, dict):
        return False
    if ev.get("success_criteria", {}).get("type") == "multi_host":
        ph = c.get("per_host")
        return isinstance(ph, list) and len(ph) > 0
    return bool(c.get("plant"))


def score_eval(ev, k, runner, require_canary=True):
    """pass@k de un eval. HARD-GATE: si `require_canary` y el eval no es canary-capable → ValueError
    (no se puntúa un gate reward-hackeable)."""
    if require_canary and not eval_is_canary_capable(ev):
        raise ValueError(f"eval '{ev.get('id')}' NO es canary-capable (sin `canary`/`per_host`): "
                         f"SkillOpt no puntúa un gate reward-hackeable. Añade el bloque canary o exclúyelo.")
    if k < 1:
        raise ValueError("k debe ser >= 1")
    passes = sum(1 for _ in range(k) if runner(ev))
    return {"eval": ev.get("id"), "k": k, "passes": passes, "pass_rate": passes / k}


def score_skill(skill_name, candidate_text, evals, k, runner,
                skills_root=DEFAULT_SKILLS_ROOT, require_canary=True, lint=True):
    """Instala la skill candidata (swap atómico + restaura), la puntúa sobre `evals` y devuelve el reward
    (media de pass@k). Antes, el lint de gobernanza puede DESCARTAR el candidato (fail-closed)."""
    if lint:
        guard.assert_skill_safe(candidate_text)   # relaja-puertas / datos-cliente → ValueError
    results = []
    with SkillSwap(skill_name, candidate_text, skills_root):
        for ev in evals:
            results.append(score_eval(ev, k, runner, require_canary))
    reward = (sum(r["pass_rate"] for r in results) / len(results)) if results else 0.0
    return {"skill": skill_name, "reward": reward, "results": results}


def shell_runner(ev, target=None, gate_timeout=3600, headroom=600):
    """Runner de PRODUCCIÓN (Kali): lanza `run_gate.py --eval <id> --canary --record` y devuelve True si el
    veredicto es PASS. Requiere el lab vivo y el provider configurado. No se usa en los tests (que inyectan
    un runner falso). Fail-safe: cualquier error → False (no cuenta como PASS).

    El `--timeout` del ENGAGEMENT (bucle de reanudación) es `gate_timeout`; el kill duro del subprocess se pone
    en `gate_timeout + headroom` para que run_gate SIEMPRE alcance a graduar + restaurar `settings.json`/
    `scope.json` + limpiar el canario en su `finally` ANTES de que el runner lo mate. Si fueran iguales (el bug
    previo: ambos 3600), el SIGKILL del runner podía caer en mitad de la limpieza y dejar el settings.json
    parcheado o tokens de canario en el lab. `headroom` cubre la limpieza del canario (hasta ~120s/host)."""
    cmd = [sys.executable, os.path.join(ROOT, "benchmark", "run_gate.py"),
           "--eval", ev["id"], "--canary", "--record", "--timeout", str(gate_timeout)]
    if target or ev.get("target", "").startswith("RELLENAR"):
        cmd += ["--target", target or ""]
    try:
        r = subprocess.run(cmd, cwd=ROOT, timeout=gate_timeout + headroom, check=False)
        return r.returncode == 0   # run_gate: exit 0 = PASS
    except (OSError, subprocess.SubprocessError):
        return False
