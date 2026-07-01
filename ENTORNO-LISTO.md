# ✅ Entorno integrado y listo para usar

Snapshot del estado tras la integración completa. Todo lo automatizable está hecho y
verificado; queda **un solo paso manual** (tu login, que no puedo hacer por ti).

## Instalado
- **Claude Code CLI** 2.1.173 (en PATH)
- **Extensión Claude Code para VS Code** 2.1.172
- **Markdown Mermaid** (`bierner.markdown-mermaid`) · **Python + Pylance** (`ms-python.python`)
- Base: Node 26 · npm 11 · Python 3.14 · git · VS Code 1.124

## Configurado e integrado
| Pieza | Estado | Verificación |
| :--- | :--- | :--- |
| **Plugin** (`plugin/`) | manifest en `plugin.json` (VS Code) **y** `.claude-plugin/plugin.json` (Claude) | `claude plugin validate ./plugin` → **✔ passed** |
| **Agents** | 21 especialistas: 11 de fase + 10 de herramienta (metasploit, recon-suite, nuclei, web-fuzzing, sqlmap, netexec, sliver, ad-enum, kerberos, adcs) | auto-descubiertos |
| **Skills** | `rag-vuln-triage`, `pentest-report` (`SKILL.md`, Open Standard) | name+description ✔ |
| **Hooks** | gate de alcance `PreToolUse` (envoltorio `{"hooks":{…}}`) | ✔ |
| **MCP Servers** | vacío en el plugin (eip no auto-arranca); eip opt-in en `.mcp.json.example` | ✔ |
| **Instructions** | `AGENTS.md` (VS Code lo reconoce) | ✔ |
| **Registro** | `chat.pluginLocations` → `plugin/` | `.vscode/settings.json` |
| **Modelos** | 6 haiku · 11 sonnet · 4 opus-4-8 (sin fable; tier de coste v1.4.0) | tuneado para Pro |
| **RAG** | store poblado: KEV + CVSS/SSVC (CVE 5.0) + EPSS + **ExploitDB + módulos Metasploit + plantillas Nuclei** | `python rag/refresh.py --epss-all` |
| **Alcance** | `contracts/scope.json` armado (placeholder de **laboratorio**) | gate fail-closed |
| **QA** | `python tools/validate_suite.py` | **463 checks OK, 0 fallos** |

## El único paso manual que queda (es tuyo)
A VS Code solo puedo hacerle clic, no escribir; y tu login es tuyo:
1. Ventana **cyberseg-agents** → `Ctrl+Shift+P` → **Reload Window** (carga el plugin).
2. Ventana de **Agents** → **Session Type → Claude** (no Copilot CLI).
3. Login con **Pro** si lo pide.
4. `/agents` → deben salir los 21. Prueba:
   `Actúa como Orquestador. Lee contracts/scope.json y usa vuln-triage para "Apache HTTP Server 2.4.49".`

## ⚠️ Antes de cada engagement real
- **Reemplaza `contracts/scope.json`** por el alcance autorizado real (ahora es un
  placeholder de laboratorio `192.168.56.0/24`). Sin scope correcto, el gate bloquea todo
  (fail-closed, seguro).
- Una VM/namespace por cliente en la zona E2; nunca mezclar engagements.
- El informe sale como borrador: **revísalo un humano** antes de entregarlo.

## Regenerar / mantener
```
python tools/build_plugin.py     # reconstruye el plugin desde .claude/agents
python tools/sync_opencode.py    # regenera el espejo opencode
python tools/gen_arch_diagram.py # regenera el mapa
python tools/validate_suite.py   # QA completo (incluye el plugin)
python rag/refresh.py --epss-all # refresca el RAG (programar a diario)
```
