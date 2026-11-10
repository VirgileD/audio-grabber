#!/usr/bin/env bash
# AudioGrabber setup, from WSL (Ubuntu):
#   1. builds AudioGrabber (Windows app), installs it to %USERPROFILE%\AudioGrabber
#      and starts it;
#   2. installs agscribe (transcription, runs in WSL) and checks that it works.
#
#   ./setup.sh                   install or update everything (keeps existing settings)
#   ./setup.sh --reconfigure     ask the questions again (folders, token, audio)
#   ./setup.sh --app-only        only build/install/start the Windows app
#   ./setup.sh --skip-app        only set up transcription
#
# First run asks: where to install AudioGrabber.exe, where recordings go, where
# transcripts go (e.g. your notes folder). Answers are remembered.
#
# Safe to re-run: only what's missing is installed; the app is rebuilt and updated.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSCRIPTION="$HERE/transcription"
BIN_DIR="$HOME/.local/bin"
LOG_DIR="$HOME/.cache/audiograbber-setup"
SETUP_CONF="$HOME/.config/audiograbber/setup.conf"   # remembered answers (install folder)
MIN_FREE_GB=10
APT_PACKAGES=(ffmpeg pulseaudio-utils ca-certificates curl)
DOTNET_CHANNEL=8.0
APP_EXE=AudioGrabber.exe

DO_APP=1
DO_TRANSCRIPTION=1
RECONFIGURE=()
ASK_AGAIN=0
for arg in "$@"; do
  case "$arg" in
    --reconfigure) RECONFIGURE=(--reconfigure); ASK_AGAIN=1 ;;
    --app-only) DO_TRANSCRIPTION=0 ;;
    --skip-app) DO_APP=0 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }
hint() { printf '    %s\n' "$@" >&2; }

mkdir -p "$LOG_DIR"

# Run a Windows command from a Windows folder (cmd.exe refuses \\wsl$ working dirs),
# with stdin disconnected: Windows programs would otherwise swallow typed answers
win() { (cd /mnt/c && "$@" </dev/null 2>/dev/null | tr -d '\r'); }

# ask "Question" "default": prints the answer (the default if empty / not interactive)
ask() {
  local answer=""
  if [[ -t 0 ]]; then
    read -r -p "  $1 [$2]: " answer
  fi
  printf '%s\n' "${answer:-$2}"
}

is_windows_path() { [[ "$1" =~ ^[A-Za-z]:[\\/] || "$1" == \\\\* ]]; }

# Windows (C:\x) or WSL (/mnt/c/x) path -> WSL path
to_wsl_path() {
  local path="${1%\"}"; path="${path#\"}"
  if is_windows_path "$path"; then wslpath -u "$path"; else realpath -m "${path/#\~/$HOME}"; fi
}

# ============================================================================
step "Checking the system"

grep -qi microsoft /proc/version 2>/dev/null \
  || die "This doesn't look like WSL: setup must run in WSL on the Windows machine that records."
ok "WSL"

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" == ubuntu || "${ID_LIKE:-}" == *ubuntu* || "${ID_LIKE:-}" == *debian* ]]; then
  ok "$PRETTY_NAME"
else
  warn "$PRETTY_NAME is not Ubuntu/Debian: system packages may need to be installed by hand (${APT_PACKAGES[*]})"
fi

[[ -d /mnt/c ]] || die "/mnt/c is not available: Windows drives must be mounted in WSL."
if [[ -z "$(win cmd.exe /c ver)" ]]; then
  hint "Enable it in /etc/wsl.conf:  [interop]  enabled=true" "then run 'wsl --shutdown' in Windows and reopen WSL."
  die "WSL can't run Windows programs (interop is disabled)."
fi
ok "Windows drives and programs reachable"

free_gb=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
(( free_gb >= MIN_FREE_GB )) \
  || die "Only ${free_gb} GB free in $HOME; about ${MIN_FREE_GB} GB is needed (build tools, libraries, models)."
ok "${free_gb} GB free"

# ============================================================================
step "System packages (${APT_PACKAGES[*]})"

missing=()
for package in "${APT_PACKAGES[@]}"; do
  dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
done
if (( ${#missing[@]} )); then
  echo "  Installing: ${missing[*]} (your sudo password may be asked)"
  sudo apt-get update -qq \
    && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" \
    || die "apt could not install: ${missing[*]} (see the messages above)."
fi
ok "System packages installed"

curl -fsS -o /dev/null --max-time 15 https://api.nuget.org/v3/index.json \
  && curl -fsS -o /dev/null --max-time 15 https://huggingface.co \
  || die "No internet access (nuget.org / huggingface.co): needed during setup only."
ok "Internet access"

# ============================================================================
install_app() {
  step "AudioGrabber (Windows app)"

  local arch
  arch=$(win cmd.exe /c 'echo %PROCESSOR_ARCHITECTURE%')
  [[ "$arch" == AMD64 ]] \
    || die "AudioGrabber is built for 64-bit x64 Windows; this Windows reports '${arch:-unknown}'."

  local win_profile install_dir settings_file output_folder
  win_profile=$(win cmd.exe /c 'echo %USERPROFILE%')
  [[ -n "$win_profile" && "$win_profile" != *%* ]] || die "Could not find the Windows user folder (%USERPROFILE%)."
  settings_file="$(wslpath -u "$win_profile")/AppData/Roaming/AudioGrabber/settings.json"

  # --- Where to install the exe (remembered in $SETUP_CONF)
  local INSTALL_DIR_WIN=""
  # shellcheck disable=SC1090
  [[ -f "$SETUP_CONF" ]] && . "$SETUP_CONF"
  if [[ -n "${AUDIOGRABBER_INSTALL_DIR:-}" ]]; then
    install_dir="$AUDIOGRABBER_INSTALL_DIR"   # for tests / scripted installs (WSL path)
  elif [[ -n "$INSTALL_DIR_WIN" ]] && (( ! ASK_AGAIN )); then
    install_dir=$(wslpath -u "$INSTALL_DIR_WIN")
  else
    install_dir=$(to_wsl_path "$(ask "Install AudioGrabber.exe in" "${INSTALL_DIR_WIN:-$win_profile\\AudioGrabber}")")
  fi
  [[ "$install_dir" == /mnt/[a-z]/* ]] \
    || die "The app must be installed in a Windows folder (C:\\..., D:\\...), not '$install_dir'."
  if [[ -z "${AUDIOGRABBER_INSTALL_DIR:-}" ]]; then
    mkdir -p "$(dirname "$SETUP_CONF")"
    printf 'INSTALL_DIR_WIN=%q\n' "$(wslpath -w "$install_dir")" >"$SETUP_CONF"
  fi
  ok "Install folder: $(wslpath -w "$install_dir")"

  # --- Where recordings go: AudioGrabber's OutputFolder setting ("./" = next to the exe)
  output_folder=$(read_output_folder "$settings_file")
  if [[ ! -f "$settings_file" ]] || (( ASK_AGAIN )); then
    echo "  Recordings folder: './' means next to AudioGrabber.exe (Windows or /mnt/... path)"
    output_folder=$(ask "Save recordings in" "${output_folder:-./}")
    if [[ "$output_folder" == /* ]]; then
      output_folder=$(wslpath -w "$(to_wsl_path "$output_folder")")
    fi
  fi
  local recordings_dir
  if is_windows_path "$output_folder"; then
    recordings_dir=$(to_wsl_path "$output_folder")
  else
    recordings_dir=$(realpath -m "$install_dir/$output_folder")   # relative to the exe
  fi
  mkdir -p "$recordings_dir" || die "Could not create the recordings folder $recordings_dir."
  ok "Recordings folder: $(wslpath -w "$recordings_dir")"

  # .NET 8 SDK, user-local (no sudo). The build needs no culture data, so run
  # .NET in invariant mode instead of requiring the ICU system library.
  export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
  if [[ -x "$HOME/.dotnet/dotnet" ]]; then
    export DOTNET_ROOT="$HOME/.dotnet" PATH="$HOME/.dotnet:$PATH"
  fi
  if ! dotnet --list-sdks 2>/dev/null | grep -q "^${DOTNET_CHANNEL%.*}\."; then
    echo "  Installing the .NET ${DOTNET_CHANNEL} SDK into ~/.dotnet (build tool, ~800 MB)"
    local installer="$LOG_DIR/dotnet-install.sh" log="$LOG_DIR/dotnet-install.log"
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o "$installer" \
      || die "Could not download the .NET installer (https://dot.net/v1/dotnet-install.sh)."
    bash "$installer" --channel "$DOTNET_CHANNEL" --install-dir "$HOME/.dotnet" >"$log" 2>&1 \
      || { tail -5 "$log" >&2; die ".NET SDK installation failed (full log: $log)."; }
    export DOTNET_ROOT="$HOME/.dotnet" PATH="$HOME/.dotnet:$PATH"
  fi
  ok ".NET SDK $(dotnet --list-sdks | grep "^${DOTNET_CHANNEL%.*}\." | tail -1 | cut -d' ' -f1)"

  # Build: self-contained (Windows needs no .NET installed), single file
  local stage log="$LOG_DIR/app-build.log"
  stage=$(mktemp -d)
  echo "  Building (Release, self-contained)..."
  if ! dotnet publish "$HERE/AudioGrabber/AudioGrabber.csproj" -c Release -r win-x64 \
      --self-contained true -p:PublishSingleFile=true -p:DebugType=none \
      -o "$stage" >"$log" 2>&1; then
    # Compiler errors, with paths relative to the repo and without the "[x.csproj]" suffix
    grep -E ': error ' "$log" | sed -e 's| \[[^]]*\]$||' -e "s|$HERE/||" | sort -u | head -15 | sed 's/^/    /' >&2 || true
    if grep -qiE 'NU1301|unable to load the service index|Name or service not known' "$log"; then
      hint "NuGet packages could not be downloaded: check the internet connection / proxy."
    fi
    die "Build failed (full log: $log)."
  fi
  ok "Built"

  # Stop running copies (installed or dev build): files are locked while running,
  # and the app only allows one instance at a time
  if win tasklist.exe /FI "IMAGENAME eq $APP_EXE" | grep -qi "$APP_EXE"; then
    echo "  Stopping the running AudioGrabber..."
    win taskkill.exe /IM "$APP_EXE" /F >/dev/null || true
    sleep 2
  fi

  # Install. Never delete anything there: recordings live in this folder too.
  mkdir -p "$install_dir" || die "Could not create $install_dir."
  if ! cp -f "$stage"/* "$install_dir"/ 2>"$log"; then
    cat "$log" >&2
    die "Could not copy the app into $install_dir (a file may be open in another program)."
  fi
  rm -rf "$stage"
  ok "Installed: $(wslpath -w "$install_dir")\\$APP_EXE"

  # The app is stopped: safe to write its settings
  write_output_folder "$settings_file" "$output_folder" \
    || die "Could not update AudioGrabber's settings ($settings_file)."

  # Start it (through Explorer: fully detached from WSL)
  local started
  started=$(date '+%Y-%m-%dT%H:%M:%S')
  win explorer.exe "$(wslpath -w "$install_dir/$APP_EXE")" || true
  sleep 5
  if win tasklist.exe /FI "IMAGENAME eq $APP_EXE" | grep -qi "$APP_EXE"; then
    ok "AudioGrabber is running (tray icon); it registers itself to start with Windows"
  else
    warn "AudioGrabber started but is not running anymore. Windows error log:"
    diagnose_app_crash "$started"
    die "AudioGrabber could not start (see above)."
  fi
}

# AudioGrabber's settings.json: read / set OutputFolder, keeping the other settings
read_output_folder() {
  [[ -f "$1" ]] || return 0
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8-sig")).get("OutputFolder") or "./")' "$1" 2>/dev/null
}

write_output_folder() {
  python3 - "$1" "$2" <<'PY'
import json, os, sys
path, folder = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
data["OutputFolder"] = folder
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8", newline="\r\n") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
}

# Show recent Windows "Application" log errors about AudioGrabber (the .NET
# crash report with the exception first)
diagnose_app_crash() {
  local since="$1" script events
  script=$(cat <<'PS'
$ProgressPreference = 'SilentlyContinue'
$since = [datetime]'__SINCE__'
Get-WinEvent -FilterHashtable @{ LogName = 'Application'; Level = 1, 2; StartTime = $since.AddSeconds(-5) } -ErrorAction SilentlyContinue |
  Where-Object { $_.Message -match 'AudioGrabber' } |
  Sort-Object { $_.ProviderName -ne '.NET Runtime' } |
  Select-Object -First 2 |
  ForEach-Object { '--- ' + $_.ProviderName + ' (' + $_.TimeCreated.ToString('HH:mm:ss') + ')'; ($_.Message -split "`n" | Select-Object -First 12) -join "`n" }
PS
)
  script=${script/__SINCE__/$since}
  # -EncodedCommand: multi-line scripts are not reliable through stdin
  events=$(cd /mnt/c && powershell.exe -NoProfile -NonInteractive \
    -EncodedCommand "$(printf '%s' "$script" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)" </dev/null 2>/dev/null | tr -d '\r')
  if [[ -n "$events" ]]; then
    printf '%s\n' "$events" | sed 's/^/    /' >&2
  else
    hint "No error found in the Windows event log." \
         "Try starting it by hand: double-click $APP_EXE in %USERPROFILE%\\AudioGrabber." \
         "Antivirus software sometimes blocks new programs: check its quarantine."
  fi
}

# ============================================================================
install_transcription() {
  step "Transcription: Python environment"

  mkdir -p "$BIN_DIR"
  export PATH="$BIN_DIR:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    echo "  Installing uv (Python package manager) into $BIN_DIR"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$BIN_DIR" UV_NO_MODIFY_PATH=1 sh >/dev/null \
      || die "Could not install uv (https://astral.sh/uv)."
  fi
  ok "uv $(uv --version | cut -d' ' -f2)"

  # Installs a project-local Python 3.12 if needed, then the exact locked versions
  local log="$LOG_DIR/uv-sync.log"
  if ! uv sync --project "$TRANSCRIPTION" --frozen --no-dev >"$log" 2>&1; then
    tail -15 "$log" >&2
    die "Installing the Python libraries failed (full log: $log)."
  fi
  ok "Python $("$TRANSCRIPTION/.venv/bin/python" -c 'import sys; print(sys.version.split()[0])') + libraries (CPU-only PyTorch)"

  ln -sfn "$TRANSCRIPTION/.venv/bin/agscribe" "$BIN_DIR/agscribe"
  ok "Command installed: $BIN_DIR/agscribe"

  step "Transcription: configuration"
  agscribe configure "${RECONFIGURE[@]}"

  step "Transcription: models (downloaded once, then everything runs offline)"
  agscribe download-models

  step "Transcription: final check (transcribes a short sample)"
  agscribe doctor
}

# ============================================================================
if (( DO_APP )); then install_app; fi
if (( DO_TRANSCRIPTION )); then install_transcription; fi

step "Ready"
if (( DO_APP )); then
  echo "  Record: press Ctrl+R (start/stop). Recordings are saved next to AudioGrabber.exe by default."
fi
if (( DO_TRANSCRIPTION )); then
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
fi
