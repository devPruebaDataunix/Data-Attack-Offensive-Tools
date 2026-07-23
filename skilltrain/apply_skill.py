#!/usr/bin/env python3
"""apply_skill.py — intercambio ATÓMICO y REVERSIBLE de una SKILL.md candidata para un rollout.

Para puntuar una skill candidata, el agente debe LEERLA como la skill instalada. Este módulo la escribe en
`plugin/skills/<name>/SKILL.md` de forma atómica, respaldando la original, y la RESTAURA en `finally` —
mismo patrón que `run_gate.py` con `scope.json` (nunca dejar el árbol de skills modificado tras la corrida).

El optimizer NUNCA edita la skill real de forma persistente: el candidato ganador se deja en
`skilltrain/out/best_skill.md` y su despliegue a `plugin/skills/` exige humano+council.
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_SKILLS_ROOT = os.path.join(ROOT, "plugin", "skills")


def skill_path(name, skills_root=DEFAULT_SKILLS_ROOT):
    """Ruta a la SKILL.md de `name`, CONFINADA bajo skills_root (rechaza traversal en el nombre)."""
    base = os.path.realpath(skills_root)
    p = os.path.realpath(os.path.join(base, name, "SKILL.md"))
    if not (p == os.path.join(base, name, "SKILL.md") or p.startswith(base + os.sep)):
        raise ValueError(f"nombre de skill fuera de zona: {name!r}")
    return p


class SkillSwap:
    """Context manager: instala `candidate_text` como la SKILL.md de `name` durante el `with`, y RESTAURA la
    original al salir (incluso si hay excepción). Escritura atómica (tmp+replace).

        with SkillSwap("web-app-security", texto_candidato):
            ... corre el rollout/score contra la skill candidata ...
        # aquí la skill original ya está restaurada
    """

    def __init__(self, name, candidate_text, skills_root=DEFAULT_SKILLS_ROOT):
        self.path = skill_path(name, skills_root)
        self.candidate_text = candidate_text
        self._backup = None

    def __enter__(self):
        if not os.path.isfile(self.path):
            raise FileNotFoundError(f"no existe la skill a swapear: {self.path}")
        self._backup = self.path + ".skilltrain.bak"
        # Crash-recovery: si quedó un backup de una corrida ANTERIOR interrumpida (SIGKILL entre swap y
        # restore), la SKILL.md actual podría ser un candidato a medio swapear. Restaura primero el ORIGINAL
        # desde ese backup, para no respaldar el candidato como si fuese el original (corrupción persistente).
        if os.path.isfile(self._backup):
            os.replace(self._backup, self.path)
        shutil.copy2(self.path, self._backup)     # respaldo del original (ya recuperado si hacía falta)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(self.candidate_text)
        os.replace(tmp, self.path)                # atómico
        return self.path

    def __exit__(self, *exc):
        # Restaura SIEMPRE el original y borra el backup.
        if self._backup and os.path.isfile(self._backup):
            os.replace(self._backup, self.path)
        return False   # no silenciar excepciones
