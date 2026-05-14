#!/bin/sh
set -e

# 1. Run database schema upgrades securely inside the container environment
echo "Running Alembic migrations..."
alembic upgrade head

# 2. Kickstart the primary web application routing process engine
echo "Starting Uvicorn web server..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}
