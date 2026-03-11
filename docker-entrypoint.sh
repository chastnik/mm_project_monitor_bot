#!/bin/sh
set -e

DATA_DIR=/app/data
mkdir -p "$DATA_DIR"

exec python main.py "$@"
