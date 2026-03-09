#!/bin/sh
set -e

DATA_DIR=/app/data
mkdir -p "$DATA_DIR"

# .crypto_salt must persist across container recreations.
# Create a symlink so crypto_utils.py writes directly into the data volume.
SALT_PERSIST="$DATA_DIR/.crypto_salt"
SALT_LOCAL="/app/.crypto_salt"

if [ -f "$SALT_PERSIST" ]; then
    ln -sf "$SALT_PERSIST" "$SALT_LOCAL"
elif [ ! -L "$SALT_LOCAL" ]; then
    ln -sf "$SALT_PERSIST" "$SALT_LOCAL"
fi

exec python main.py "$@"
