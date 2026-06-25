# CaveBridge — Colossal Cave Adventure with an LLM Dungeon Master front-end.
#
# Build:
#   docker build -t cavebridge .
#
# Run (point OPENAI_BASE_URL at your LLM; use host.docker.internal for a local one):
#   docker run -it --rm \
#     -e OPENAI_BASE_URL=http://host.docker.internal:1234/v1 \
#     -e OPENAI_API_KEY=lm-studio \
#     -e OPENAI_MODEL=qwen/qwen3.5-9b \
#     -e CAVEBRIDGE_LANG=zh \
#     -v cavebridge-saves:/root/.cavebridge \
#     cavebridge
#
# On native-Linux Docker add:  --add-host=host.docker.internal:host-gateway
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libedit-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Build the -j/autosave engine (make_dungeon.py needs pyyaml) and install deps.
# Note: no `make clean` — the COPY is already a fresh tree, and `make clean`
# recurses into tests/ (excluded by .dockerignore), which would loop forever.
RUN pip install --no-cache-dir pyyaml openai \
    && make CFLAGS="-DADVENT_AUTOSAVE"

ENV CAVEBRIDGE_LANG=zh
ENTRYPOINT ["python", "-m", "cavebridge"]
