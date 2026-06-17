# =============================================================================
#  Data Attack — Offensive Tools :: imagen de despliegue
#  Kali rolling + toolchain ofensivo + Claude Code + el repo, para un primer
#  despliegue reproducible en contenedor. REUTILIZA deploy/lib.sh (install_missing)
#  para no duplicar la lista de herramientas: misma fuente que el deploy de host.
#
#  Build/run SOLO en un host con Docker (la Kali). Ver DEPLOY.md → "Contenedores".
#  La autenticación Pro de Claude Code y el token del bot NO se hornean: se montan
#  en runtime (docker-compose.yml: ~/.claude y bot/.env).
# =============================================================================
FROM kalilinux/kali-rolling

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/go/bin:/root/.local/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin"

WORKDIR /opt/data-attack

# El repo (sin secretos ni venv ni db — ver .dockerignore).
COPY . /opt/data-attack

# Base: utilidades + Python + Go + Node LTS (Claude Code requiere Node >=18).
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl wget jq ca-certificates gnupg build-essential \
      python3 python3-pip python3-venv pipx python-is-python3 golang-go dnsutils \
 && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
 && apt-get install -y nodejs

# Permisos de ejecución (por si el contexto de build perdió el bit +x) + toolchain ofensivo
# + Claude Code + opencode + gum, vía el MISMO install_missing del deploy de host (DRY).
# install_missing es tolerante (un componente que falle no aborta el resto).
RUN chmod +x deploy/*.sh && bash -c '. deploy/lib.sh && install_missing'

# Entorno del bot (venv aislado; textual ya viene en requirements para la TUI).
RUN python3 -m venv bot/.venv \
 && bot/.venv/bin/pip install --no-cache-dir --upgrade pip \
 && bot/.venv/bin/pip install --no-cache-dir -r bot/requirements.txt

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# El RAG se puebla en runtime (servicio rag-init) para no hornear CVEs caducos.
# Comando por defecto = el bot; compose lo sobreescribe para rag-init / shell.
ENTRYPOINT ["/bin/bash", "-lc"]
CMD ["cd bot && ./.venv/bin/python bot.py"]
