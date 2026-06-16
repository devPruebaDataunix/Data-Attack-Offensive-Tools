"""
Clasificación de comandos por NIVEL DE RIESGO y POLÍTICA DE APROBACIÓN humana.

Sustituye al regex binario `OFFENSIVE` ("ofensivo sí/no") por una graduación de 5
niveles con una política de aprobación por nivel, alineada con la CONSTITUTION
(humano-en-el-bucle, no daño) y con la intención del operador:
  - el recon pasivo NO debe generar fricción (auto-aprueba);
  - lo destructivo (robo de credenciales, impacto) SIEMPRE pregunta;
  - el C2 / implantes piden DOBLE confirmación.

Niveles (severidad creciente) y política:
  safe        recon pasivo / 3rd-party / solo lectura        -> auto  (sin preguntar)
  normal      escaneo / fuzzing ACTIVO no destructivo        -> ask   (1 OK)
  sensitive   sondas de explotación / brute / enum auth      -> ask   (1 OK)
  destructive impacto real / robo de credenciales / RCE      -> ask   (1 OK, aviso fuerte)
  critical    C2 / implantes / generación de payloads        -> dual  (2 OK)

Determinista y sin dependencias (regex stdlib) -> testeable sin el Agent SDK.
Un comando que toque varias herramientas toma el MÁXIMO nivel.
Política de un comando sin herramienta conocida (p.ej. `ls`) = auto (benigno),
mismo criterio que el antiguo allowlist `OFFENSIVE`.
"""
from __future__ import annotations

import re

# Tokens (nombres de binario/herramienta) por nivel. Se comparan con \b...\b, case-insensitive.
TIERS: dict[str, list[str]] = {
    "safe": [
        "whois", "dig", "nslookup", "subfinder", "amass", "gau", "waybackurls",
        "theharvester", "sublist3r", "assetfinder", "dnsx",
    ],
    "normal": [
        "nmap", "naabu", "masscan", "rustscan", "httpx", "nuclei", "nikto",
        "gobuster", "ffuf", "feroxbuster", "dirb", "dirsearch", "wfuzz",
        "katana", "wpscan", "wafw00f", "gospider", "hakrawler",
    ],
    "sensitive": [
        "sqlmap", "commix", "dalfox", "hydra", "medusa", "patator", "ncrack",
        "ldapsearch", "kerbrute", "enum4linux", "certipy", "getuserspns",
        "getnpusers", "smbmap", "john", "hashcat", "bloodhound",
    ],
    "destructive": [
        "msfconsole", "msfcli", "metasploit", "meterpreter", "netexec", "nxc",
        "crackmapexec", "cme", "secretsdump", "mimikatz", "psexec", "wmiexec",
        "smbexec", "atexec", "dcomexec", "evil-winrm", "responder", "ntlmrelayx",
        "lsassy", "nanodump",
    ],
    "critical": [
        "sliver", "cobaltstrike", "cobalt", "havoc", "mythic", "empire",
        "merlin", "koadic", "msfvenom",
    ],
}

# Severidad creciente: la clasificación devuelve el primer match recorriendo de mayor a menor.
TIER_ORDER = ("safe", "normal", "sensitive", "destructive", "critical")

# Política de aprobación humana por nivel.
TIER_POLICY = {
    "safe": "auto",
    "normal": "ask",
    "sensitive": "ask",
    "destructive": "ask",
    "critical": "dual",
}


def _rx(tokens: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in tokens) + r")\b", re.I)


_TIER_RX = {tier: _rx(tokens) for tier, tokens in TIERS.items()}

# Compat: el antiguo `OFFENSIVE` = cualquier herramienta que NO sea recon pasivo (todo lo que pregunta).
_NONSAFE = [t for tier in ("normal", "sensitive", "destructive", "critical") for t in TIERS[tier]]
OFFENSIVE = _rx(_NONSAFE)


def classify_command(cmd: str) -> tuple[str, str]:
    """Devuelve (tier, policy). tier='benign' si no toca ninguna herramienta conocida."""
    cmd = cmd or ""
    for tier in reversed(TIER_ORDER):          # critical -> ... -> safe
        if _TIER_RX[tier].search(cmd):
            return tier, TIER_POLICY[tier]
    return "benign", "auto"


def tools_in(cmd: str) -> list[str]:
    """Herramientas reconocidas en el comando (para logging/depuración)."""
    found = []
    for tier in TIER_ORDER:
        for m in _TIER_RX[tier].finditer(cmd or ""):
            found.append(m.group(1).lower())
    return found
