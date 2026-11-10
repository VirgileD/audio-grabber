#!/usr/bin/env bash
# agscribe setup: installs everything needed to transcribe AudioGrabber recordings
# in WSL (Ubuntu), then checks that it all works.
#
#   ./setup.sh                 install / repair (keeps existing settings)
#   ./setup.sh --reconfigure   also ask all configuration questions again
#
# Safe to re-run: only what's missing is installed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
MIN_FREE_GB=10
APT_PACKAGES=(ffmpeg pulseaudio-utils ca-certificates curl)

RECONFIGURE=()
case "${1:-}" in
  "") ;;
  --reconfigure) RECONFIGURE=(--reconfigure) ;;
  -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Unknown option: $1 (try --help)" >&2; exit 1 ;;
esac

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# ----------------------------------------------------------------------------
step "Checking the system"

grep -qi microsoft /proc/version 2>/dev/null \
  || die "This doesn't look like WSL. agscribe needs WSL to reach the Windows recordings."
ok "WSL"

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" == ubuntu || "${ID_LIKE:-}" == *ubuntu* || "${ID_LIKE:-}" == *debian* ]]; then
  ok "$PRETTY_NAME"
else
  warn "$PRETTY_NAME is not Ubuntu/Debian: system packages may need to be installed by hand (${APT_PACKAGES[*]})"
fi

free_gb=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
(( free_gb >= MIN_FREE_GB )) \
  || die "Only ${free_gb} GB free in $HOME; about ${MIN_FREE_GB} GB is needed (libraries + models)."
ok "${free_gb} GB free"

[[ -d /mnt/c ]] || die "/mnt/c is not available: Windows drives must be mounted in WSL."
ok "Windows drives mounted"

# ----------------------------------------------------------------------------
step "System packages (${APT_PACKAGES[*]})"

missing=()
for package in "${APT_PACKAGES[@]}"; do
  dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
done
if (( ${#missing[@]} )); then
  echo "  Installing: ${missing[*]} (your sudo password may be asked)"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
fi
ok "System packages installed"

curl -fsS -o /dev/null --max-time 15 https://huggingface.co \
  || die "Can't reach huggingface.co: an internet connection is needed for setup."
ok "Internet access"

# ----------------------------------------------------------------------------
step "Python environment"

mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "  Installing uv (Python package manager) into $BIN_DIR"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$BIN_DIR" UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
ok "uv $(uv --version | cut -d' ' -f2)"

# Installs a project-local Python 3.12 if needed, then the exact locked versions
uv sync --project "$HERE" --frozen --no-dev --quiet
ok "Python $("$HERE/.venv/bin/python" -c 'import sys; print(sys.version.split()[0])') + libraries (CPU-only PyTorch)"

ln -sfn "$HERE/.venv/bin/agscribe" "$BIN_DIR/agscribe"
ok "Command installed: $BIN_DIR/agscribe"

# ----------------------------------------------------------------------------
step "Configuration"
agscribe configure "${RECONFIGURE[@]}"

step "Models (downloaded once, then everything runs offline)"
agscribe download-models

step "Final check (transcribes a short sample)"
agscribe doctor

# ----------------------------------------------------------------------------
step "Ready"
if ! bash -lc 'command -v agscribe' >/dev/null 2>&1; then
  warn "$BIN_DIR is not in your PATH for new shells. Add this line to ~/.bashrc:"
  echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
cat <<'EOF'
  After a recording (open a new terminal first if agscribe isn't found):
    agscribe transcribe     transcribe new recordings
    agscribe name           name the speakers it doesn't know yet
    agscribe --help         all commands
EOF
