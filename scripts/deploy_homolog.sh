#!/usr/bin/env bash
set -euo pipefail

project=skynet-homolog
case "${1:-up}" in
  up) docker compose -p "$project" up -d --build --wait ;;
  down) docker compose -p "$project" down -v ;;
  *) echo "uso: scripts/deploy_homolog.sh [up|down]" >&2; exit 2 ;;
esac
