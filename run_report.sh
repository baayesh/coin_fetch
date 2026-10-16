#!/usr/bin/env bash
# Runs coin_fetch.py with the project's venv, for use from cron.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec .venv/bin/python coin_fetch.py
