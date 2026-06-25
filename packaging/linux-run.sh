#!/bin/bash
# Launch CaveBridge from anywhere: ./run.sh
cd "$(dirname "$0")" || exit 1
exec ./cavebridge
