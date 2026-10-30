#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "$script_dir/.." && pwd)"

if command -v psql >/dev/null 2>&1; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is not set. Export your Neon PostgreSQL connection string first." >&2
    exit 1
  fi
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$script_dir/seed_amenities.sql"
else
  python_cmd="${PYTHON:-python}"
  if [[ -z "${PYTHON:-}" && -x "$project_dir/env/Scripts/python.exe" ]]; then
    python_cmd="$project_dir/env/Scripts/python.exe"
  fi
  "$python_cmd" "$script_dir/run_seed_sql.py"
fi
