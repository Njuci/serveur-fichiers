#!/bin/sh
set -eu

if [ ! -f "$DATA_DIR/users.json" ]; then
    cp /app/data/users.json "$DATA_DIR/users.json"
fi

exec "$@"
