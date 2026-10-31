#!/usr/bin/env sh
# Install and start Retro locally:   curl -fsSL https://raw.githubusercontent.com/devhimanshuhc/retro/main/install.sh | sh
# Installs into ~/retro (override with RETRO_DIR), starts everything and opens the browser, which asks for your API key.
set -eu

REPO="${RETRO_REPO:-devhimanshuhc/retro}"
BRANCH="${RETRO_BRANCH:-main}"
DIR="${RETRO_DIR:-$HOME/retro}"
RAW="https://raw.githubusercontent.com/$REPO/$BRANCH/deploy"
PORT="${RETRO_WEB_PORT:-3000}"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf 'retro: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is required: install Docker Desktop (https://docs.docker.com/get-docker/) and run this again."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (it comes with Docker Desktop)."
docker info >/dev/null 2>&1 || die "Docker is installed but not running: start Docker Desktop and run this again."

mkdir -p "$DIR" && cd "$DIR"
say "Downloading Retro into $DIR"
curl -fsSL "$RAW/compose.yaml" -o compose.yaml
curl -fsSL "$RAW/.env.example" -o .env.example

[ -f .env ] || { cp .env.example .env; chmod 600 .env; }  # the API key is added in the browser, on first open

say "Starting Retro (the first run downloads a few GB of images)"
docker compose pull --quiet || die "couldn't download Retro's images. To build from source instead: git clone https://github.com/$REPO && cd retro/deploy && cp $DIR/.env . && docker compose up -d --build"
docker compose up -d

printf 'Waiting for Retro to be ready'
i=0
until curl -fsS -o /dev/null "http://localhost:$PORT/" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -gt 120 ] && die "Retro didn't start in time. Look at: cd $DIR && docker compose logs"
  printf '.'; sleep 2
done
echo
say "Retro is running at http://localhost:$PORT (add your Anthropic or OpenAI API key when it opens)"
echo "Stop:    cd $DIR && docker compose down"
echo "Update:  cd $DIR && docker compose pull && docker compose up -d"
(open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT") >/dev/null 2>&1 || true
