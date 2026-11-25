#!/bin/bash
# Placeholder until the stream engine ships; the box auto-updates every 10 min.
LANG_=$1
if [ -f /opt/gph/stream/engine.py ]; then exec /opt/venv/bin/python /opt/gph/stream/engine.py "$LANG_"; fi
echo "stream engine not deployed yet ($LANG_)"; sleep 600
