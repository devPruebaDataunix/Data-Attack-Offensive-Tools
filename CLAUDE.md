# Data Attack — instrucciones del proyecto

El cerebro de coordinacion (el **playbook del Orquestador**) vive en `AGENTS.md`. Claude Code (CLI)
NO auto-carga `AGENTS.md` como instrucciones del proyecto: solo lee `CLAUDE.md`. Por eso este
fichero lo **importa**, para que la sesion principal cargue el playbook tanto en la CLI como en el
bot/TUI (que corren con `setting_sources=["project"]`). Manten el contenido en `AGENTS.md`; aqui
solo se importa una vez (sin duplicar).

@AGENTS.md
