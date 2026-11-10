#!/usr/bin/env bash
# Build AudioGrabber in WSL and run it on Windows.
#
#   ./run.sh          build, deploy to Windows, and start the app (default)
#   ./run.sh build    build only (quick compile check)
#   ./run.sh stop     stop the running app on Windows
#   ./run.sh release  publish a Release build to the deploy folder (doesn't start it)
#
# The app is deployed to %USERPROFILE%\AudioGrabberDev on the Windows side,
# because Windows apps started from inside the WSL filesystem (\\wsl$\...) are
# slow and sometimes misbehave.
set -euo pipefail

cd "$(dirname "$0")"

# Use the user-local .NET SDK if dotnet isn't already on PATH.
if ! command -v dotnet >/dev/null 2>&1 && [ -x "$HOME/.dotnet/dotnet" ]; then
  export DOTNET_ROOT="$HOME/.dotnet"
  export PATH="$DOTNET_ROOT:$PATH"
fi
export DOTNET_CLI_TELEMETRY_OPTOUT=1

PROJECT="AudioGrabber/AudioGrabber.csproj"
EXE_NAME="AudioGrabber.exe"

win_profile="$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')"
DEPLOY_DIR="$(wslpath "$win_profile")/AudioGrabberDev"

stop_app() {
  if tasklist.exe /FI "IMAGENAME eq $EXE_NAME" 2>/dev/null | grep -qi "$EXE_NAME"; then
    echo "Stopping running $EXE_NAME..."
    taskkill.exe /IM "$EXE_NAME" /F >/dev/null
    sleep 1   # let Windows release file locks
  fi
}

publish() {
  local config="$1"
  stop_app   # the running exe locks its files
  echo "Publishing ($config) to $DEPLOY_DIR ..."
  dotnet publish "$PROJECT" -c "$config" -r win-x64 --self-contained false \
    -o "$DEPLOY_DIR" -nologo -v quiet
}

case "${1:-run}" in
  build)
    dotnet build "$PROJECT" -nologo
    ;;
  stop)
    stop_app
    ;;
  release)
    publish Release
    echo "Done: $DEPLOY_DIR/$EXE_NAME"
    ;;
  run)
    publish Debug
    echo "Starting $EXE_NAME on Windows (look for the tray icon)..."
    # Launch through Explorer so the app is fully detached from WSL; launching
    # it directly (or via cmd "start") keeps this terminal attached until it exits.
    # explorer.exe always returns exit code 1, hence the "|| true".
    explorer.exe "$(wslpath -w "$DEPLOY_DIR/$EXE_NAME")" || true
    echo "Running. Use './run.sh stop' to quit it."
    ;;
  *)
    echo "Usage: $0 [run|build|stop|release]" >&2
    exit 1
    ;;
esac
