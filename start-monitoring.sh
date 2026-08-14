#!/bin/bash
# Bring up the monitoring stack and start the collector.
#
# Configuration comes from .env (copy .env.example). This script deliberately
# exports nothing itself: an earlier version exported User/Password/Instance/
# Database, which no code reads, so a correctly filled .env was ignored and the
# collector connected to nothing.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and fill it in first." >&2
  exit 1
fi

# The collector needs a database to observe. Fail here with a clear message
# rather than inside psycopg2 several seconds later.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

missing=()
for var in DB_HOST DB_NAME DB_USER; do
  [ -n "${!var:-}" ] || missing+=("$var")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing required settings in .env: ${missing[*]}" >&2
  exit 1
fi

echo "Restarting the monitoring stack..."
docker compose down --remove-orphans
docker compose up -d

# Dependencies live in the container; the collector runs on the host. Check the
# imports resolve before backgrounding, because a backgrounded failure exits
# instantly and the old script still printed "started" over the top of it.
if ! python3 -c "import psycopg2, requests" 2>/dev/null; then
  echo "Host Python is missing dependencies. Run: pip install -r requirements.txt" >&2
  exit 1
fi

# Poll interval is read from MONITOR_INTERVAL_SECONDS. monitor_and_alert.py has
# no argument parser, so the --interval/--continuous flags the old script passed
# were silently ignored and the interval was never what it claimed.
echo "Starting database monitoring (interval: ${MONITOR_INTERVAL_SECONDS:-300}s)..."
python3 monitor_and_alert.py > event.log 2>&1 &
pid=$!

# Give it a moment to fail on connection or import errors, then confirm it is
# actually alive instead of reporting success unconditionally.
sleep 2
if ! kill -0 "$pid" 2>/dev/null; then
  echo "Monitoring failed to start. Last lines of event.log:" >&2
  tail -20 event.log >&2
  exit 1
fi

echo "Monitoring started with PID: $pid"
echo "Log file: event.log"
