#!/bin/sh
#
# Start Habitat under a persistent PSGI server (much faster than CGI).
# Existing runlocal.sh (CGI via python3 -m http.server) keeps working
# unchanged; pick whichever runner you prefer.
#
# Defaults to `plackup` (single-process, fine for local dev).
# Override with HABITAT_PSGI_SERVER=Starman (or any Plack::Handler::*)
# for multi-worker production use.
#
# Env vars:
#   HABITAT_PORT          (default 51712)
#   HABITAT_PSGI_SERVER   (default plackup; e.g. Starman, Twiggy)
#   HABITAT_WORKERS       (only honored by Starman; default 4)

set -e

CGIDIR=$(dirname "$0")
PORT=${HABITAT_PORT:-51712}
SERVER=${HABITAT_PSGI_SERVER:-plackup}
WORKERS=${HABITAT_WORKERS:-4}

"$CGIDIR/stoppsgi.sh" 2>/dev/null || true

cd "$CGIDIR"

case "$SERVER" in
    plackup|Plackup)
        exec plackup -p "$PORT" app.psgi
        ;;
    starman|Starman)
        exec starman --workers "$WORKERS" --listen "127.0.0.1:$PORT" app.psgi
        ;;
    *)
        # Generic: use plackup with -s <Handler>
        exec plackup -s "$SERVER" -p "$PORT" app.psgi
        ;;
esac
