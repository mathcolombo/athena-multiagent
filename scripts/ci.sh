#!/usr/bin/env bash
set -euo pipefail

service="${1:?uso: scripts/ci.sh <catalog|cart|orders>}"
floor="${COV_FLOOR:-55}"

pytest libs/events/tests -q
node --test "web/tests/*.test.js"
pytest "services/${service}/tests" "--cov=${service}_service" "--cov-fail-under=${floor}" -q
