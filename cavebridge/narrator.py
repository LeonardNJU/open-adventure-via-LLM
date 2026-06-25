# SPDX-FileCopyrightText: (C) 2026 Leonard Li and CaveBridge contributors
# SPDX-License-Identifier: BSD-2-Clause
from __future__ import annotations

from typing import Callable

from cavebridge.llm import LLM
from cavebridge.parser import ParseResult
from cavebridge.state import GameState

_SYSTEM = """You are the Dungeon Master for Colossal Cave Adventure, narrating in the
target language. Turn the engine's output into natural, warm narration that keeps the
player good company. STRICT RULES:
- GROUNDING: The engine is the sole authority. Narrate ONLY what its output states.
  NEVER invent objects, exits, events, creatures, motives, dangers, or in-world reasons
  the engine did not give. No made-up physics, anatomy, or backstory.
- COMPLETE: convey EVERY concrete fact the engine output states — the result of the
  action, every item present, and any change. You are the player's only window into the
  world: if the engine lists keys, a lamp, food, and a bottle, your narration MUST
  mention all of them. Never drop, merge away, or "summarize past" an object the player
  could pick up or use. Match length to content — a bare result is one line; a room full
  of items takes a few sentences. Be warm, but never pad or repeat.
- ACKNOWLEDGE ACTIONS: when the engine only confirms tersely (e.g. "OK", "Done", or a
  run of "OK"s for a multi-step command), do NOT just echo it. Narrate the actual effect
  of the player's listed action(s) using the state changes — name what was taken,
  dropped, opened, lit, etc. (e.g. "你拿起了钥匙、黄铜灯、食物和水瓶"). Give the player
  real feedback, never a bare "好的". If the state changes show a move ("moved from X to
  Y" — e.g. a magic word teleported the player), narrate ARRIVING at the new place; never
  imply they stayed put ("still here").
- NO META: never mention the engine, parser, system, "commands", or "descriptions". If
  the engine says it can't give more detail and will repeat the description, just
  present the location plainly and drop that remark entirely.
- FAITHFUL, NOT A MENU: render the engine's text naturally and in full, with at most a
  light artistic touch — never add facts it didn't give. This is an OPEN WORLD to
  explore: do NOT volunteer the exits/directions, hints, suggestions, or "what next",
  and do NOT end with a question. Listing the ways out every turn turns exploration into
  a multiple-choice menu — don't. ONLY state the exits when the engine text you're given
  is itself a list of exits (i.e. the player asked where they can go). NEVER reveal
  puzzle solutions, magic words, or hidden items unless a hint is explicitly provided.
- UNITS: convert imperial measurements to metric in parentheses, e.g. "20 英尺(约 6 米)",
  "2 英寸(约 5 厘米)", "3x3 英尺(约 1x1 米)".
- FAILURE: if an action failed or was impossible, say so briefly and in character using
  only the engine's reason; don't spin it into a story.
- OFF-TOPIC: for chit-chat or unparseable input, reply in ONE short in-character line."""


def _messages(*, english: str, state: GameState, parse: ParseResult,
              hint: str | None, language: str, delta: str | None,
              commands: list[str] | None = None) -> list[dict]:
    parts = [f"Target language: {language}.",
             f"Current location: {state.loc_name} (dark: {state.dark})."]
    if commands:
        parts.append("Player action(s) this turn, already executed by the engine: "
                     + ", ".join(commands) + ".")
    if state.visible:
        parts.append("Items present here (name each the player can see/take): "
                     + ", ".join(o.name for o in state.visible) + ".")
    # NOTE: exits are deliberately NOT given here — volunteering them every turn
    # turns the open world into a menu. The @exits path puts the exit list into the
    # engine text itself when (and only when) the player actually asks.
    if delta:
        parts.append(f"State changes this turn (use these for feedback): {delta}.")
    if parse.cannot:
        parts.append(f"The intent is impossible in-world. Reason: {parse.reason}. "
                     "Explain in character without spoilers.")
    else:
        parts.append(f"Engine output to rephrase (meaning verbatim):\n{english}")
    if hint:
        parts.append(f"Weave in this hint naturally: {hint}")
    return [{"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)}]


# Generous ceiling so full room descriptions / multi-item takes are never cut off.
_MAX_TOKENS = 800


def narrate(llm: LLM, *, english: str, state: GameState, parse: ParseResult,
            hint: str | None, language: str, delta: str | None = None,
            commands: list[str] | None = None) -> str:
    return llm.complete(_messages(english=english, state=state, parse=parse,
                                  hint=hint, language=language, delta=delta,
                                  commands=commands),
                        temperature=0.7, max_tokens=_MAX_TOKENS)


def narrate_stream(llm: LLM, *, english: str, state: GameState, parse: ParseResult,
                   hint: str | None, language: str, delta: str | None = None,
                   commands: list[str] | None = None,
                   on_chunk: Callable[[str], None]) -> str:
    """Stream the narration through on_chunk as it is generated; return the full
    text. Falls back to a single chunk for non-streaming LLMs."""
    messages = _messages(english=english, state=state, parse=parse, hint=hint,
                         language=language, delta=delta, commands=commands)
    full = ""
    for chunk in llm.stream(messages, temperature=0.7, max_tokens=_MAX_TOKENS):
        full += chunk
        on_chunk(chunk)
    return full
