#!/bin/bash
# Double-click this to play CaveBridge on macOS.
# CaveBridge is unsigned, so macOS "quarantines" downloaded files and may say
# "Python.framework is damaged". Nothing is wrong — this clears that flag and launches.
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine . 2>/dev/null || true
exec ./cavebridge
