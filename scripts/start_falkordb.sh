#!/usr/bin/env bash
# Start a local FalkorDB instance without Docker.
#
# What this script does:
#   1. Checks redis-server exists and is Redis 7.4+.
#   2. Downloads the matching FalkorDB release module (.so) if missing.
#   3. Starts redis-server with FalkorDB loaded as a Redis module.
#
# Usage:
#   bash scripts/start_falkordb.sh
#
# Optional environment variables:
#   FALKORDB_VERSION=v4.18.10          # FalkorDB release tag to download
#   FALKORDB_MODULE_DIR=.cache/falkordb # Where downloaded .so files are stored
#   REDIS_HOST=127.0.0.1               # Bind host
#   REDIS_PORT=6379                    # Bind port
#
# After this script is running, open another terminal and verify with:
#   uv run python examples/e2e_falkordb.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FALKORDB_VERSION="${FALKORDB_VERSION:-v4.18.10}"
FALKORDB_MODULE_DIR="${FALKORDB_MODULE_DIR:-$PROJECT_ROOT/.cache/falkordb}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_MIN_MAJOR="${REDIS_MIN_MAJOR:-7}"
REDIS_MIN_MINOR="${REDIS_MIN_MINOR:-4}"

log() {
  printf '[zig:falkordb] %s\n' "$*" >&2
}

fail() {
  printf '[zig:falkordb] ERROR: %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

print_usage() {
  cat <<'EOF'
Start a local FalkorDB instance without Docker.

Usage:
  bash scripts/start_falkordb.sh

What it does:
  1. Checks redis-server exists and is Redis 7.4+.
  2. Downloads the matching FalkorDB release module (.so) if missing.
  3. Starts redis-server with FalkorDB loaded as a Redis module.

Optional environment variables:
  FALKORDB_VERSION=v4.18.10           FalkorDB release tag to download
  FALKORDB_MODULE_DIR=.cache/falkordb Directory for downloaded .so files
  REDIS_HOST=127.0.0.1                Redis bind host
  REDIS_PORT=6379                     Redis bind port

Examples:
  bash scripts/start_falkordb.sh
  FALKORDB_VERSION=v4.18.10 bash scripts/start_falkordb.sh
  REDIS_PORT=6380 bash scripts/start_falkordb.sh

After startup, verify in another terminal:
  uv run python examples/e2e_falkordb.py
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_usage
  exit 0
fi

detect_release_asset() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"

  case "$os:$arch" in
    Darwin:arm64|Darwin:aarch64)
      printf 'falkordb-macos-arm64v8.so'
      ;;
    Linux:x86_64)
      printf 'falkordb-x64.so'
      ;;
    Linux:arm64|Linux:aarch64)
      printf 'falkordb-arm64v8.so'
      ;;
    Darwin:x86_64)
      return 2
      ;;
    *)
      return 1
      ;;
  esac
}

release_download_url() {
  local asset="$1"
  printf 'https://github.com/FalkorDB/FalkorDB/releases/download/%s/%s' "$FALKORDB_VERSION" "$asset"
}

release_module_path() {
  local asset="$1"
  printf '%s/%s/%s' "$FALKORDB_MODULE_DIR" "$FALKORDB_VERSION" "$asset"
}

print_redis_install_instructions() {
  cat >&2 <<'EOF'
[zig:falkordb] redis-server is required because FalkorDB runs as a Redis module.

Install Redis manually, then rerun this script.

macOS (Homebrew):
  brew install redis
  redis-server --version

Ubuntu / Debian:
  sudo apt-get update
  sudo apt-get install redis-server
  redis-server --version

Fedora:
  sudo dnf install redis
  redis-server --version

RHEL / CentOS:
  sudo yum install redis
  redis-server --version

Arch Linux:
  sudo pacman -S redis
  redis-server --version

Requirement:
  Redis 7.4+ is required by FalkorDB.
EOF
}

ensure_redis_server() {
  if ! command_exists redis-server; then
    print_redis_install_instructions
    fail "redis-server not found in PATH"
  fi

  ensure_redis_version
}

ensure_redis_version() {
  local version major minor
  version="$(redis-server --version | sed -n 's/.*v=\([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1.\2/p')"
  [[ -n "$version" ]] || fail "Unable to detect redis-server version"

  major="${version%%.*}"
  minor="${version#*.}"

  if (( major < REDIS_MIN_MAJOR || (major == REDIS_MIN_MAJOR && minor < REDIS_MIN_MINOR) )); then
    print_redis_install_instructions
    fail "Redis $REDIS_MIN_MAJOR.$REDIS_MIN_MINOR+ is required by FalkorDB, found $version. Upgrade Redis and rerun this script."
  fi

  log "redis-server version OK: $version"
}

ensure_prerequisites() {
  command_exists curl || fail "curl not found. Install curl or download FalkorDB release artifact manually."
  ensure_redis_server
}

download_release_module() {
  local asset module url status

  set +e
  asset="$(detect_release_asset)"
  status=$?
  set -e

  if [[ "$status" == "2" ]]; then
    fail "FalkorDB $FALKORDB_VERSION does not publish a macOS x86_64 release module. Current platform: $(uname -s)/$(uname -m). The release provides macOS arm64 only."
  fi
  if [[ "$status" != "0" || -z "$asset" ]]; then
    fail "No FalkorDB release asset mapping for platform: $(uname -s)/$(uname -m)"
  fi

  module="$(release_module_path "$asset")"

  if [[ -f "$module" ]]; then
    log "Found FalkorDB release module: $module"
    printf '%s' "$module"
    return 0
  fi

  mkdir -p "$(dirname "$module")"
  url="$(release_download_url "$asset")"

  log "Downloading FalkorDB release module"
  log "Version: $FALKORDB_VERSION"
  log "Asset: $asset"
  log "URL: $url"

  if ! curl -L --fail --output "$module" "$url"; then
    rm -f "$module"
    fail "Failed to download FalkorDB release artifact. Check version/asset exists: $url"
  fi

  chmod 0644 "$module"
  log "Downloaded FalkorDB module: $module"
  printf '%s' "$module"
}

start_redis_with_falkordb() {
  local module="$1"

  log "Starting redis-server with FalkorDB module"
  log "Host: $REDIS_HOST"
  log "Port: $REDIS_PORT"
  log "Module: $module"
  log "Press Ctrl+C to stop"

  exec redis-server --bind "$REDIS_HOST" --port "$REDIS_PORT" --loadmodule "$module"
}

ensure_prerequisites
MODULE_PATH="$(download_release_module)"
start_redis_with_falkordb "$MODULE_PATH"
