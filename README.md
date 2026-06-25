<!--
SPDX-FileCopyrightText: (C) 2026 Leonard Li and CaveBridge contributors
SPDX-License-Identifier: BSD-2-Clause
-->

**English** · [简体中文](README.zh.md)

<p align="center">
  <img src="assets/hero.png" width="860"
       alt="CaveBridge — a natural-language interface for deterministic text-adventure worlds">
</p>

# Open Adventure × LLM — *CaveBridge*

> Play the 1977 classic **Colossal Cave Adventure** in natural language — an LLM
> Dungeon Master front-end that adds a modern, forgiving interface and narrates in any
> language your model speaks, while the original game engine stays the single source of truth.

CaveBridge wraps Eric S. Raymond's [Open Adventure](README-open-adventure.adoc) C
engine. It does **not** reimplement the game. An LLM sits in front of the unmodified
engine and does exactly two jobs:

1. **Understand** — turn your free-form text ("grab the lamp and light it", "take
   everything", "follow the stream down until you reach the grate") into the engine's
   canonical commands.
2. **Narrate** — retell the engine's terse output as a warm Dungeon Master, in your
   language.

The C engine remains the single, authoritative world model. The LLM never invents
rooms, items, or events and never mutates game state — so you get the full,
deterministic 1977 puzzle intact, with a 21st-century interface on top. The essence:
**promote the old engine to a verifiable world model, demote the LLM to a language
interface.**

---

## Highlights

- **Natural language in, any phrasing** — no need to learn `VERB NOUN`; type how you talk.
- **Narration in your language** — English, 中文, or anything else your model speaks;
  switchable mid-game with `/lang`. (The built-in how-to-play guide ships in EN/中文.)
- **Grounded, no fabrication, no spoilers** — narration is bound to engine output;
  hints only when you ask (`/hint`) or opt in (`/hints on`).
- **Penalty-free saves** — the original *charges score* to save; here every turn is
  autosaved for free, plus named slots (`/save`, `/load`).
- **Multi-step commands** — "take everything", "go north then open the grate".
- **Auto-advance** — "keep heading downstream until you reach the grate"; an LLM judge
  stops the loop on the goal, danger, or a stall.
- **Raw view** — see the exact canonical command(s) and the engine's own text (`/raw`).
- **"The DM is writing…"** indicator while the model generates, replaced by the narration.

### Purist mode

Prefer the unembellished 1977 experience? Turn the modern conveniences **off** and keep
only the parts that don't change gameplay — natural-language translation and DM
narration. In purist mode you get **one action per turn** (no batching, no auto-walk)
and no hints, exactly like the original — just understandable and in your language.

```
/purist on          # in-game, or set CAVEBRIDGE_PURIST=1 at launch
```

Or flip features individually: `/multistep on|off`, `/autoadvance on|off`, `/hints on|off`.

---

## See it in action

You just talk — multi-step actions ("take everything, leave"), asking where you can go,
following the stream downstream to the locked grate. The `⟦cmd⟧` / `⟦raw⟧` lines (toggle
with `/raw`) reveal the exact canonical command and the engine's own output behind each
turn, so nothing is hidden.

<p align="center">
  <img src="assets/screenshot-play.png" width="900"
       alt="Natural-language play: take everything, ask for exits, follow the stream to the grate">
</p>

A new game opens with a how-to-play guide and the DM narrating the first scene:

<p align="center">
  <img src="assets/screenshot-guide.png" width="640"
       alt="Startup guide and the DM narrating the opening scene">
</p>

---

## Quick start

You need an **OpenAI-compatible** chat endpoint — LM Studio, Ollama, or vLLM running
locally, or a hosted one. You do **not** have to set environment variables: on first
run CaveBridge asks for the endpoint URL, key, and model name and remembers them. Change
them anytime in-game with `/config`.

> Tip for local models: disable "thinking"/reasoning mode for snappier turns.

### Tested models

Any OpenAI-compatible chat model works. These three are tested and play well:

| Model | Where / cost | Endpoint (`base`) |
|---|---|---|
| `gemini-3.1-flash-lite` | Google AI Studio — has a free tier | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `deepseek-v4-flash` | DeepSeek API — very cheap | `https://api.deepseek.com/v1` |
| `qwen3.5-9B` | self-hosted (LM Studio / Ollama / vLLM) | `http://localhost:1234/v1` |

Set the connection on first run, with `/config` in-game, or via env vars. Example for
Google's free Gemini tier:

```bash
export OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
export OPENAI_API_KEY="<your Google AI Studio key>"
export OPENAI_MODEL="gemini-3.1-flash-lite"
```

### Download a prebuilt binary (recommended)

Self-contained builds — no Python, no compiler, no dependencies — are attached to
[**Releases**](../../releases). The first launch walks you through connecting to your LLM.

- **Windows** — download `cavebridge-windows-x86_64.exe`. Double-click it (it opens its
  own console window) or run it from PowerShell/cmd.
- **macOS** — download `cavebridge-macos-arm64.tar.gz`. It's a command-line program, so
  **run it from Terminal, not by double-clicking** (double-clicking just opens the raw
  file in a text editor). It's unsigned, so clear Gatekeeper's quarantine flag once:
  ```bash
  tar xzf cavebridge-macos-arm64.tar.gz
  xattr -dr com.apple.quarantine cavebridge-macos-arm64   # allow an unsigned binary
  ./cavebridge-macos-arm64/cavebridge
  ```
- **Linux** — download `cavebridge-linux-x86_64.tar.gz`, extract, and run from a terminal:
  ```bash
  tar xzf cavebridge-linux-x86_64.tar.gz
  ./cavebridge-linux-x86_64/cavebridge
  ```

### Build from source (Linux / macOS)

Needs a C toolchain + `libedit`, and Python 3.11+ with [uv](https://docs.astral.sh/uv/).

```bash
make CFLAGS="-DADVENT_AUTOSAVE"          # build the engine the front-end drives
uv venv && uv pip install pyyaml openai
uv run python -m cavebridge             # first run asks for your LLM details
```

### Docker (any OS, including Windows without the prebuilt exe)

```bash
docker build -t cavebridge .
docker run -it --rm \
  -e OPENAI_BASE_URL=http://host.docker.internal:1234/v1 \
  -e OPENAI_API_KEY=lm-studio \
  -e OPENAI_MODEL=qwen/qwen3.5-9b \
  -v cavebridge-saves:/root/.cavebridge \
  cavebridge
```

`host.docker.internal` reaches an LLM on your host (on native-Linux Docker add
`--add-host=host.docker.internal:host-gateway`). `-it` is required.

---

## Playing

Type what you want in plain language. At startup you choose **resume vs. new**, and a
new game offers a how-to-play guide.

| Command | What it does |
|---|---|
| `/guide` | How-to-play guide |
| `/help` | List commands |
| `/config` | Show / change the LLM connection (`/config model <name>`, `base`, `key`, `lang`) |
| `/hint` · `/hints on｜off` | One hint · auto-hints when stuck |
| `/lang <language>` | Switch narration language (e.g. `en`, `zh`, `français`, …) |
| `/raw on｜off` | Show/hide the canonical command + engine output |
| `/purist on｜off` | Faithful 1977 mode (translation + narration only) |
| `/multistep on｜off` · `/autoadvance on｜off` | Toggle conveniences individually |
| `/save <name>` · `/load <name>` | Named save slots (penalty-free) |
| `/new` · `/quit` | New game · quit (progress is autosaved) |

---

## Configuration

The connection is resolved as **environment variable → saved config → first-run
wizard**, so any of these works:

- Just run it and answer the prompts (saved to `~/.cavebridge/config.json`).
- Change it later with `/config` in-game.
- Or set environment variables (handy for Docker / scripting):

| Var | Default | Meaning |
|---|---|---|
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` | — | LLM endpoint (overrides the saved config) |
| `CAVEBRIDGE_LANG` | `en` | narration language — `en`, `zh`, or any language your model speaks |
| `CAVEBRIDGE_PURIST` | `0` | `1` = faithful mode (multi-step + auto-advance + hints off) |
| `CAVEBRIDGE_MULTISTEP` | `1` | several actions per line |
| `CAVEBRIDGE_AUTOADVANCE` | `1` | "keep going until …" loops |
| `CAVEBRIDGE_HINTS` | `0` | `1` to start with auto-hints on |
| `CAVEBRIDGE_RAW` | `1` | `0` to hide the raw view |
| `CAVEBRIDGE_SEED` | `1` | RNG seed for reproducible games |
| `CAVEBRIDGE_SAVE_DIR` | `~/.cavebridge` | where saves/autosave/config live |

---

## How it works

A small, **build-gated** patch to the C engine (active only under the `-j` runtime flag)
makes it scriptable: it prints prompt sentinels and a one-line `@state` JSON snapshot,
and autosaves each turn. With the default build the engine is byte-for-byte unchanged and
its 100+ test regression suite still passes. The Python front-end (`cavebridge/`) drives
the engine over plain pipes, parses your intent against the game's real vocabulary, and
narrates each result. Exits, batch commands, and loops are resolved from the engine's own
state — never guessed.

---

## License & Credits

Free and open source under **BSD-2-Clause** — the same as upstream Open Adventure — so
anyone may play, modify, and redistribute it.

- **Colossal Cave Adventure** — © 1977, 2005 Will Crowther and Don Woods (original game).
- **Open Adventure** (the C engine, forward-port) — © Eric S. Raymond
  <esr@thyrsus.com>, BSD-2-Clause. See [`COPYING`](COPYING) and the upstream README,
  preserved here as [`README-open-adventure.adoc`](README-open-adventure.adoc).
- Some assets/docs are CC-BY-4.0 or MIT-0 (see per-file `SPDX-License-Identifier` headers).
- **CaveBridge** (the `cavebridge/` LLM front-end) — © 2026 Leonard Li and CaveBridge
  contributors, BSD-2-Clause.

The original engine and all its copyright notices are retained unmodified, as the license
requires.
