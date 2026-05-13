#!/bin/sh
#
# Stop a plackup/starman instance previously started with runpsgi.sh.

PORT=${HABITAT_PORT:-51712}

# Prefer killing by the port that PSGI server is bound to (works for
# plackup, starman, twiggy alike). Falls back to a name match.
PIDS=$(ss -tlnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p { print $0 }' \
        | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)

if [ -z "$PIDS" ]; then
    PIDS=$(pgrep -f "plackup .* :?$PORT|starman .* :?$PORT" || true)
fi

if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null || true
    sleep 1
    # Force-kill any survivors.
    for pid in $PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
fi
