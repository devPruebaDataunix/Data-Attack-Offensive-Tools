#!/usr/bin/env python3
"""optimize.py — bucle de SkillOpt (rollout→reflect→score→select→GATE heldout). LAB-ONLY, build-time.

Orquesta la optimización de una skill. Los pasos que LANZAN modelo/agente (`rollout`, `reflect`) son *seams*
inyectables: en Kali se pasan implementaciones reales (lanzan `run_gate`/provider contra labs); aquí, sin
inyectarlos, `run()` falla con un mensaje claro y `--dry-run` enseña el plan sin ejecutarlos.

Garantías cableadas (ver README): reward SOLO por PASS canario (scorer HARD-GATE), lint de gobernanza a cada
candidato, GATE en heldout (anti-overfit), y escritura confinada a `skilltrain/out/`.

Uso:
    python skilltrain/optimize.py --config skilltrain/config.json --dry-run
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Salida UTF-8 robusta (consola Windows cp1252 revienta con '→'/'…'); en Kali ya es UTF-8.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmark"))
import guard                                   # noqa: E402
import scorer                                  # noqa: E402
from run_eval import load_evals                # noqa: E402  (benchmark/run_eval.py)

OUT_DIR = os.path.join(HERE, "out")
SKILLS_ROOT = os.path.join(ROOT, "plugin", "skills")


def load_config(path):
    return json.load(open(path, encoding="utf-8"))


def current_skill_text(skill, skills_root=SKILLS_ROOT):
    return open(os.path.join(skills_root, skill, "SKILL.md"), encoding="utf-8").read()


def resolve_evals(config):
    """(train, heldout) como listas de dicts de eval. Marca cuáles son canary-capable (el scorer solo
    puntúa esos)."""
    train = list(load_evals(config.get("train_split", "train")).values())
    heldout = list(load_evals(config.get("heldout_split", "heldout")).values())
    return train, heldout


def dry_run_plan(config):
    """Imprime el plan completo SIN lanzar rollouts/reflect (para revisar la integración)."""
    train, heldout = resolve_evals(config)
    def _tag(evs):
        return [f"{e['id']}{'' if scorer.eval_is_canary_capable(e) else '  (NO canary-capable → EXCLUIDO)'}"
                for e in evs]
    print(f"== SkillOpt plan ==")
    print(f"skill objetivo : {config['skill']}  (plugin/skills/{config['skill']}/SKILL.md)")
    print(f"provider       : {config.get('provider', 'opencode')}  | k={config.get('k', 3)} | "
          f"max_iters={config.get('max_iters', 5)} | candidatos/iter={config.get('candidates_per_iter', 3)}")
    print(f"train  ({len(train)}): " + ", ".join(_tag(train)))
    print(f"heldout({len(heldout)}): " + ", ".join(_tag(heldout)))
    print(f"reward         : media pass@k con run_gate --canary (SOLO evals canary-capable)")
    print(f"aceptación     : {config.get('accept_on', 'heldout_improves')} (GATE en heldout, anti-overfit)")
    print(f"salida         : {os.path.relpath(OUT_DIR, ROOT)}/best_skill.md  (NO auto-aplicado; humano+council)")
    n_train_ok = sum(1 for e in train if scorer.eval_is_canary_capable(e))
    n_held_ok = sum(1 for e in heldout if scorer.eval_is_canary_capable(e))
    print(f"\ncanary-capable : train {n_train_ok}/{len(train)} · heldout {n_held_ok}/{len(heldout)}")
    if n_train_ok == 0 or n_held_ok == 0:
        print("[!] AVISO: faltan evals canary-capable en train o heldout → añade bloques `canary`/`per_host` "
              "antes de correr (el scorer se negará a puntuar sin canario).", file=sys.stderr)


def write_best(text):
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "best_skill.md")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)
    return p


def _seam_rollout(skill_text, train_evals):
    raise NotImplementedError(
        "rollout requiere labs vivos + provider: inyecta `rollout_fn` (Kali). Aquí usa --dry-run.")


def _seam_reflect(skill_text, transcripts, n):
    raise NotImplementedError(
        "reflect lanza el LLM: inyecta `reflect_fn` (Kali). Aquí usa --dry-run.")


def run(config, runner, rollout_fn=_seam_rollout, reflect_fn=_seam_reflect, skills_root=SKILLS_ROOT):
    """Bucle de optimización. `runner`/`rollout_fn`/`reflect_fn` se inyectan en Kali. Devuelve el mejor
    texto de skill (y lo deja en out/best_skill.md). Reward y GATE usan SOLO el scorer canario."""
    accept_on = config.get("accept_on", "heldout_improves")
    if accept_on != "heldout_improves":
        raise ValueError(f"accept_on='{accept_on}' no soportado; la única política es 'heldout_improves' "
                         f"(GATE anti-overfit en heldout).")
    train, heldout = resolve_evals(config)
    train = [e for e in train if scorer.eval_is_canary_capable(e)]
    heldout = [e for e in heldout if scorer.eval_is_canary_capable(e)]
    if not train or not heldout:
        raise ValueError("faltan evals canary-capable en train o heldout (añade bloques canary/per_host).")
    skill, k = config["skill"], config.get("k", 3)
    current = current_skill_text(skill, skills_root)
    baseline = scorer.score_skill(skill, current, heldout, k, runner, skills_root)["reward"]
    best_reward = baseline
    print(f"[skilltrain] baseline heldout reward = {baseline:.3f}")
    for it in range(config.get("max_iters", 5)):
        transcripts = rollout_fn(current, train)
        candidates = reflect_fn(current, transcripts, config.get("candidates_per_iter", 3))
        scored = []
        for cand in candidates:
            if guard.lint_skill(cand):        # descarta candidatos que relajan puertas / traen datos cliente
                continue
            scored.append((scorer.score_skill(skill, cand, train, k, runner, skills_root)["reward"], cand))
        if not scored:
            continue
        _, cand = max(scored, key=lambda x: x[0])   # mejor candidato en train
        held = scorer.score_skill(skill, cand, heldout, k, runner, skills_root)["reward"]
        if held > best_reward:              # GATE anti-overfit: solo si MEJORA el mejor heldout hasta ahora
            print(f"[skilltrain] iter {it}: ACEPTADO (heldout {held:.3f} > umbral {best_reward:.3f})")
            current, best_reward = cand, held
            write_best(current)
        else:
            print(f"[skilltrain] iter {it}: rechazado (heldout {held:.3f} <= {best_reward:.3f})")
    write_best(current)
    return current


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--dry-run", action="store_true", help="enseña el plan sin lanzar rollouts/reflect")
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.dry_run:
        dry_run_plan(cfg)
        return
    print("[skilltrain] correr el bucle real requiere labs vivos + provider (Kali): inyecta runner/rollout/"
          "reflect desde el arnés de Kali, o usa --dry-run.", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
