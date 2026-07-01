#!/usr/bin/env python3
"""
apply_routing.py — Cambia el PERFIL de routing del espejo opencode (lab) y regenera el espejo.

El espejo opencode (.opencode/agent/*.md) se enruta con tools/routing.json. Este helper intercambia
ese fichero entre perfiles versionados y re-corre sync_opencode.py para aplicarlo. SOLO afecta a
opencode (laboratorio): el bot real de engagements y la medición OFICIAL del GATE siguen 100% Anthropic
(run_gate.py lanza `claude`, no opencode). El espejo opencode NO ejecuta los hooks deterministas
(scope_guard/C1-C19) ni el bus A2A — es inherente a opencode, no al provider.

Perfiles:
  nvidia-lab   -> aplica tools/routing.nvidia-lab.json: 20 agentes de recon/explotación a modelos
                  FREE de NVIDIA NIM (corrobora el cableado sin gastar Anthropic). El Orquestador y
                  knowledge-postmortem se quedan en Anthropic.
  default      -> restaura el routing activo previo (el que hubiera antes de aplicar un perfil) desde el
                  backup tools/routing.json.bak; si no existe, lo restaura desde git (HEAD) — pero NO
                  descarta cambios locales sin commitear: si los hay, aborta y te pide revisarlos.

Uso:
    python tools/apply_routing.py nvidia-lab
    python tools/apply_routing.py default

LAB-ONLY. Solo stdlib.
"""
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ACTIVE = os.path.join(HERE, "routing.json")
BAK = ACTIVE + ".bak"


def _profiles():
    """{nombre: ruta} de los perfiles versionados tools/routing.<nombre>.json (excluye el activo)."""
    out = {}
    for p in glob.glob(os.path.join(HERE, "routing.*.json")):
        name = os.path.basename(p)[len("routing."):-len(".json")]
        out[name] = p
    return out


def _sync():
    """Regenera .opencode/agent/*.md con el routing recién escrito."""
    r = subprocess.run([sys.executable, os.path.join(HERE, "sync_opencode.py")], cwd=ROOT, check=False)
    return r.returncode == 0


def apply_profile(name, profiles):
    src = profiles[name]
    # Respalda el perfil ACTIVO una sola vez (para poder volver al default sin depender de git).
    if not os.path.isfile(BAK):
        shutil.copy2(ACTIVE, BAK)
        print(f"[apply] routing activo respaldado -> {os.path.basename(BAK)} (gitignored)")
    shutil.copy2(src, ACTIVE)
    print(f"[apply] perfil '{name}' aplicado a tools/routing.json")
    print("[apply] AVISO: el espejo opencode NO corre hooks deterministas ni A2A; corrobora cableado, "
          "no es la medición oficial (esa = Claude, run_gate.py). LAB-ONLY.")
    if _sync():
        return 0
    print("[!] routing.json quedó aplicado pero sync_opencode.py FALLÓ: el espejo .opencode/agent NO se "
          "regeneró. Corre 'python tools/sync_opencode.py' a mano, o revierte con 'apply_routing.py "
          "default'.", file=sys.stderr)
    return 1


def restore_default():
    if os.path.isfile(BAK):
        shutil.copy2(BAK, ACTIVE)
        os.remove(BAK)
        print("[apply] routing.json restaurado desde el backup (.bak) y backup eliminado")
    else:
        # Sin backup: restaurar desde git (HEAD). NUNCA machacar cambios locales sin avisar: el operador
        # pudo editar routing.json a mano (cambiar de modelo es un flujo legítimo, ver su $comment).
        try:
            chk = subprocess.run(["git", "diff", "--quiet", "--", "tools/routing.json"], cwd=ROOT)
        except FileNotFoundError:
            print("[!] no hay backup (.bak) y git no está disponible; restaura tools/routing.json a mano "
                  "y corre sync_opencode.py.", file=sys.stderr)
            return 2
        if chk.returncode == 1:
            print("[!] no hay backup (.bak) y tools/routing.json tiene CAMBIOS LOCALES sin commitear; NO "
                  "los descarto. Revísalos y restáuralo tú (git checkout -- tools/routing.json si quieres "
                  "perderlos), luego corre python tools/sync_opencode.py.", file=sys.stderr)
            return 2
        if chk.returncode != 0:
            print("[!] no hay backup (.bak) y no pude consultar git (¿no es un repo?); restaura "
                  "tools/routing.json a mano.", file=sys.stderr)
            return 2
        subprocess.run(["git", "checkout", "--", "tools/routing.json"], cwd=ROOT, check=False)
        print("[apply] routing.json restaurado desde git (HEAD; sin cambios locales que perder)")
    return 0 if _sync() else 1


def main():
    profiles = _profiles()
    choices = ["default", *sorted(profiles)]
    if len(sys.argv) != 2 or sys.argv[1] not in choices:
        print(f"uso: apply_routing.py <{'|'.join(choices)}>", file=sys.stderr)
        sys.exit(2)
    sys.exit(restore_default() if sys.argv[1] == "default" else apply_profile(sys.argv[1], profiles))


if __name__ == "__main__":
    main()
