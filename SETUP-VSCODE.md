# Arranque en VS Code — entorno listo

## Estado del entorno (ya instalado)
- ✅ **Claude Code CLI** 2.1.173 (`claude`, en PATH)
- ✅ **Extensión Claude Code para VS Code** 2.1.172 (`anthropic.claude-code`)
- ✅ **Markdown Preview Mermaid** (`bierner.markdown-mermaid`) — renderiza `ARCHITECTURE_MAP.md`
- ✅ **Python + Pylance** (`ms-python.python`) — para los scripts de `rag/`
- ✅ Node 26 · npm 11 · Python 3.14 · git · VS Code 1.123.2

## Pasos finales (los haces tú una vez)

1. **Abre la carpeta como workspace** (la raíz debe ser `cyberseg-agents/` para que se
   cargue `.claude/`):
   ```
   code "C:\Users\Alvaro\Claude-Fable5_Cyberseguidad\cyberseg-agents"
   ```
2. **Inicia sesión** (suscripción Pro): abre un terminal integrado en VS Code y ejecuta
   `claude`. Sigue el login por navegador (OAuth). Solo la primera vez.
3. **Confirma que los agentes cargan**: en la sesión de Claude Code escribe `/agents`.
   Deben aparecer los 23 especialistas (recon, analysis, exploitation, closing).
4. **Define el alcance autorizado** antes de cualquier acción:
   ```
   copy contracts\scope.example.json contracts\scope.json
   ```
   y edítalo con los dominios/IPs del engagement (o del laboratorio de pruebas).
5. **Puebla el RAG de vulnerabilidades**:
   ```
   python rag\refresh.py --epss-all
   ```
6. **Verifica que todo está correcto** (linter de la suite):
   ```
   python tools\validate_suite.py
   ```

A partir de aquí, la sesión principal de Claude Code actúa de **Orquestador**: delega en los
subagentes (hub-and-spoke) y **enruta el bus A2A mediado** entre ellos. El hook `scope_guard`
bloquea cualquier comando fuera de `scope.json`, `budget_guard`/`a2a_guard` aplican los techos
(acciones y hops A2A), y el hook del mapa regenera `ARCHITECTURE_MAP.md` solo.

## Modelos y coste (importante en plan Pro)

**Decisión (tu hardware no da para LLM local útil): todo en Claude Pro, con tiers afinados.**
Se quitó `CLAUDE_CODE_SUBAGENT_MODEL` de `.claude/settings.json` (forzaba *todos* los
subagentes a `fable` y quemaba cupo). Ahora manda el `model` de cada agente:

| Modelo | Agentes | Por qué |
| :--- | :--- | :--- |
| `claude-haiku-4-5` | osint-recon, recon-suite, active-recon, web-fuzzing, nuclei, knowledge-postmortem | recon/escaneo/parseo mecánico: mucho dato, poco razonamiento (sin `effort`) |
| `claude-sonnet-4-6` | vuln-triage, sqlmap, metasploit, netexec, sliver, lateral-discovery, c2-exfil, network-exploit | tool-driving con juicio / el RAG hace el trabajo pesado |
| `claude-opus-4-8` | web-exploit, post-exploit, ai-security, reporting | razonamiento ofensivo pesado + informe |

**Orquestador** (sesión principal): elígelo al abrir la sesión. `sonnet` para engagements
rutinarios; `opus-4-8` para los complejos.

> Modelos locales/gratis descartados para *esta* máquina (Ryzen 7 5825U, 15 GB RAM, GPU
> integrada): un 3B por CPU sería lento y no sirve para triage/explotación/informe. Si en el
> futuro usas un equipo con GPU, se puede cablear opencode + Ollama para tareas triviales sin
> datos de cliente (el espejo `.opencode/agent/` ya existe).
