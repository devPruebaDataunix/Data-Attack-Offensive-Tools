#!/usr/bin/env bash
# =============================================================================
#  deploy/banner.sh — Banner de Data Attack (logo ASCII + wordmark) con la
#  paleta de la herramienta (cian #00D4FF de marca, rojo para lo ofensivo).
#  Source-able (define da_banner) y ejecutable (lo imprime). Sin dependencias:
#  degrada a texto plano si no hay TTY o si NO_COLOR está definido.
#  Los .txt viven en assets/banners/ (data-attack.txt + dataunix.txt).
# =============================================================================
_DA_BANNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../assets/banners" 2>/dev/null && pwd || true)"

da_banner() {
  local cy='' dm='' rs='' bd=''
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    cy=$'\e[38;2;0;212;255m'    # cian de marca
    dm=$'\e[38;2;139;148;158m'  # gris atenuado
    bd=$'\e[1m'; rs=$'\e[0m'
  fi
  local dir="${_DA_BANNER_DIR:-}"
  if [ -n "$dir" ] && [ -f "$dir/data-attack.txt" ]; then
    printf '%s%s\n' "$bd$cy" ""; cat "$dir/data-attack.txt"; printf '%s' "$rs"
  else
    printf '\n%s  DATA ATTACK%s\n' "$bd$cy" "$rs"
  fi
  if [ -n "$dir" ] && [ -f "$dir/dataunix.txt" ]; then
    printf '%s' "$dm"; cat "$dir/dataunix.txt"; printf '%s' "$rs"
  fi
  printf '  %sOffensive Tools%s %s·%s %spentest autorizado%s\n\n' "$cy" "$rs" "$dm" "$rs" "$dm" "$rs"
}

# Si se ejecuta directamente, imprime el banner.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then da_banner; fi
