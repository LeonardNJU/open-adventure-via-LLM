# SPDX-FileCopyrightText: (C) 2026 Leonard Li and CaveBridge contributors
# SPDX-License-Identifier: BSD-2-Clause
from __future__ import annotations

import os
import traceback
from typing import Callable

from cavebridge import diag
from cavebridge.config import save_config
from cavebridge.engine import Engine, Turn
from cavebridge.guide import guide
from cavebridge.hints import HintManager
from cavebridge.llm import LLM
from cavebridge.narrator import narrate, narrate_stream
from cavebridge.parser import ParseResult, judge_loop_stop, parse_intent, parse_yes_no
from cavebridge.saves import SaveStore
from cavebridge.settings import Settings
from cavebridge.state import GameState
from cavebridge.vocab import Vocab

_HELP = ("Commands: /help /guide /hint /hints on|off /raw on|off /lang en|zh "
         "/purist on|off /multistep on|off /autoadvance on|off /config /report "
         "/save <name> /load <name> /new /quit  (anything else is spoken to the DM)")
_NEUTRAL = ParseResult(commands=["(answer)"], cannot=False, reason=None)

# Keep ~100 turns of full-text history before a one-time compaction: the oldest
# turns are summarised and the most recent _HISTORY_KEEP are kept verbatim.
_HISTORY_COMPACT_AT = 100
_HISTORY_KEEP = 20


def _delta(prev: GameState | None, cur: GameState) -> str | None:
    if prev is None:
        return None
    parts: list[str] = []
    pinv, cinv = {o.id for o in prev.inventory}, {o.id for o in cur.inventory}
    got = [o.name for o in cur.inventory if o.id in cinv - pinv]
    lost = [o.name for o in prev.inventory if o.id in pinv - cinv]
    if got:
        parts.append("now carrying: " + ", ".join(got))
    if lost:
        parts.append("no longer carrying: " + ", ".join(lost))
    if prev.loc != cur.loc:
        # from -> to so the narration reflects the move (e.g. an xyzzy teleport),
        # instead of reading "You're inside building" as "still inside".
        parts.append(f"moved from {prev.loc_name} to {cur.loc_name}")
    if prev.flags.get("closed") != cur.flags.get("closed"):
        parts.append("the cave is now closed")
    return "; ".join(parts) or None


def run_repl(*, settings: Settings, engine: Engine, llm: LLM, vocab: Vocab,
             input_fn: Callable[[], str], output_fn: Callable[[str], None],
             hints: HintManager | None = None, saves: SaveStore | None = None,
             engine_factory: Callable[[], Engine] | None = None,
             stream_fn: Callable[[str], None] | None = None,
             notify_fn: Callable[[str | None], None] | None = None,
             config_path: str | None = None,
             narrate_intro: bool = False, resume: bool = False) -> None:
    hints = hints or HintManager(enabled=settings.hints_enabled)
    save_dir = os.path.dirname(config_path) if config_path else None
    diag_state: dict = {"line": "", "snapshot": None}   # cur input + last snapshot

    def confirm(question: str) -> bool:
        """Ask a yes/no question by reading the next input line."""
        output_fn(question)
        try:
            ans = input_fn().strip().lower()
        except (EOFError, StopIteration):
            return False
        return (ans[:1] in ("y", "1")
                or any(k in ans for k in ("是", "对", "好", "覆盖", "确", "yes")))

    def persist_config() -> None:
        if config_path:
            try:
                save_config(config_path, {"base_url": settings.base_url,
                                          "api_key": settings.api_key,
                                          "model": settings.model,
                                          "language": settings.language})
            except Exception:
                pass

    def take_snapshot(kind: str, summary: str, detail: str) -> str | None:
        """Write a sanitized error snapshot (never the api_key); remember it for /report."""
        if not save_dir:
            return None
        try:
            text = diag.build_report(
                kind=kind, summary=summary, detail=detail,
                base_url=settings.base_url, model=settings.model,
                language=settings.language, player_input=diag_state["line"],
                location=getattr(current, "loc_name", "?"), recent=history)
            if settings.api_key:                 # belt-and-suspenders: never leak the key
                text = text.replace(settings.api_key, "***REDACTED***")
            path = diag.save_snapshot(save_dir, kind, text)
            diag_state["snapshot"] = (path, text)
            return path
        except Exception:
            return None

    history: list[str] = []      # recent "input -> observation" for the parser
    pending_ask: str | None = None
    ended = False

    def record(player: str, observation: str) -> None:
        obs = " ".join(observation.split())          # full observation, one line
        history.append(f"you: {player!r} -> {obs}")
        # Append-only keeps the cached prefix growing (only the new turn re-prefills).
        # Compact only on a threshold -> one-time cache reset, bounded context.
        if len(history) > _HISTORY_COMPACT_AT:
            old, recent = history[:-_HISTORY_KEEP], history[-_HISTORY_KEEP:]
            try:
                summary = llm.complete(
                    [{"role": "system", "content":
                      "Summarize these Colossal Cave Adventure turns in 2-4 terse "
                      "sentences (places, items taken, key events). No spoilers."},
                     {"role": "user", "content": "\n".join(old)}],
                    temperature=0.0)
                history[:] = [f"[earlier: {' '.join(summary.split())[:500]}]"] + recent
            except Exception:
                history[:] = recent

    def emit_raw(commands: list[str] | None, english: str) -> None:
        if not settings.show_raw:
            return
        if commands:
            output_fn("  ⟦cmd⟧ " + " → ".join(commands))
        if english and english.strip():
            output_fn("  ⟦raw⟧ " + english.strip().replace("\n", "\n        "))

    def show(*, english, state, parse, hint, delta, commands=None) -> None:
        # "DM is writing…" placeholder while the LLM generates; cleared the moment
        # real output is ready (first stream chunk, or the finished text).
        notify = notify_fn or (lambda _msg: None)
        notify("🎲 DM 正在输入…" if settings.language == "zh" else "🎲 The DM is writing…")
        if stream_fn is not None:
            cleared = False

            def on_chunk(s: str) -> None:
                nonlocal cleared
                if not cleared:
                    cleared = True
                    notify(None)         # erase the placeholder before the first words
                stream_fn(s)

            full = narrate_stream(llm, english=english, state=state, parse=parse,
                                  hint=hint, language=settings.language, delta=delta,
                                  commands=commands, on_chunk=on_chunk)
            if not full.strip():
                # The model produced nothing — retry once non-streaming. If it's
                # STILL empty, fall back to the engine's own text and warn the player
                # (their endpoint/model is the likely culprit) + snapshot it.
                retry = narrate(llm, english=english, state=state, parse=parse,
                                hint=hint, language=settings.language,
                                delta=delta, commands=commands).strip()
                shown = retry or english.strip()
                if shown:
                    if not cleared:
                        cleared = True
                        notify(None)
                    stream_fn(shown)
                if not retry:
                    zh = settings.language == "zh"
                    note = ("\n\n⚠️ 模型这一轮没有任何回复（上面是引擎原文）。多半是你的 LLM "
                            "端点/模型有问题——请检查 /config 是否有效；可继续操作，仍不行就用 "
                            "/report 一键上报。" if zh else
                            "\n\n⚠️ The model returned nothing this turn (raw game text is "
                            "above). Your LLM endpoint/model is the likely issue — check "
                            "/config; you can keep playing, and /report files a bug.")
                    if not cleared:
                        cleared = True
                        notify(None)
                    stream_fn(note)
                    take_snapshot("empty-narration",
                                  "model returned empty narration",
                                  "engine text was:\n" + (english or "(none)"))
            if not cleared:              # nothing streamed -> remove the placeholder
                notify(None)             # (when chunks DID arrive it's already gone;
            stream_fn("\n")              #  clearing again would erase the last line)
        else:
            text = narrate(llm, english=english, state=state, parse=parse,
                          hint=hint, language=settings.language, delta=delta,
                          commands=commands)
            notify(None)
            output_fn(text)

    def present_intro(turn: Turn) -> None:
        if narrate_intro and turn.kind == "normal":
            emit_raw([], turn.text)
            show(english=turn.text, state=turn.state, parse=_NEUTRAL,
                 hint=None, delta=None)
        else:
            output_fn(turn.text)
        record("(start)", turn.text)

    start_turn = engine.start(fresh=not resume)
    if start_turn.kind == "ended" and resume and engine_factory:
        # corrupt / incompatible save -> fall back to a fresh game
        engine.close()
        try:
            os.remove(settings.autosave_path)
        except OSError:
            pass
        engine = engine_factory()
        start_turn = engine.start(fresh=True)
    if start_turn.kind == "ended":
        output_fn(start_turn.text)
        engine.close()
        return
    current = start_turn.state
    hints.observe(current)
    present_intro(start_turn)

    def process(turn: Turn, parse: ParseResult, prev: GameState,
                commands: list[str] | None = None) -> None:
        nonlocal current, pending_ask, ended
        if turn.kind == "ended":
            ended = True
            output_fn(turn.text)
            return
        if turn.kind == "ask":
            pending_ask = turn.question
            show(english=turn.text, state=current, parse=parse, hint=None, delta=None,
                 commands=commands)
            return
        pending_ask = None
        new = turn.state
        delta = _delta(prev, new)
        hints.observe(new)
        hint = hints.maybe_hint(llm, new, vocab, settings.language)
        current = new
        show(english=turn.text, state=new, parse=parse, hint=hint, delta=delta,
             commands=commands)

    def run_turn(line: str, prev: GameState) -> None:
        if pending_ask is not None:
            yes = parse_yes_no(llm, pending_ask, line, settings.language)
            t = engine.answer(yes)
            emit_raw(["yes" if yes else "no"], t.text)
            process(t, _NEUTRAL, prev, ["yes" if yes else "no"])
            record(line, t.text)
            return

        parse = parse_intent(llm, current, history, line, vocab, settings.language,
                             multi_step=settings.multi_step,
                             auto_advance=settings.auto_advance)
        if parse.cannot:
            show(english="", state=current, parse=parse, hint=None, delta=None)
            record(line, parse.reason or "(couldn't do that)")
            return
        # Execute the command sequence. Pseudo-commands are resolved against the
        # LATEST state: @takeall/@dropall expand after any preceding move (fixes
        # "enter then take all"); @exits is answered from state, no engine call.
        texts: list[str] = []
        info: list[str] = []
        sent: list[str] = []          # real engine commands (for the raw view)
        turn = None
        state_now = current
        queue = list(parse.commands)
        if not settings.multi_step:
            queue = queue[:1]                     # purist: exactly one action / turn
        guard = 0
        while queue and guard < 40:
            guard += 1
            cmd = queue.pop(0)
            low = cmd.strip().lower()
            if low in ("@takeall", "@dropall"):
                verb = "drop" if low == "@dropall" else "take"
                objs = state_now.inventory if verb == "drop" else state_now.visible
                if not settings.multi_step:
                    objs = objs[:1]               # purist: one item, not a batch
                queue[:0] = [f"{verb} {o.name}" for o in objs]
                continue
            if low in ("@exits", "exits"):
                info.append("Exits from here: " +
                            (", ".join(state_now.exits) or "none obvious") + ".")
                continue
            if low in ("@save", "save"):
                if saves:
                    try:
                        saves.save("quick", settings.autosave_path)
                    except Exception:
                        pass
                info.append("Saved. (The game also autosaves every turn — your "
                            "progress is never lost.) Use /save <name> for a named "
                            "slot and /load <name> to restore it.")
                continue
            if low in ("@load", "resume"):
                info.append("The game autosaves every turn, so progress is kept. To "
                            "jump back to a named save, use /load <name>.")
                continue
            if low.startswith("@repeat"):
                parts = cmd.split(":", 2)
                rep_cmd = (parts[1].strip() if len(parts) > 1 else "") or "look"
                goal = parts[2].strip() if len(parts) > 2 else "advance"
                if not settings.auto_advance:             # purist: a single step
                    sent.append(rep_cmd)
                    turn = engine.step(rep_cmd)
                    if turn.text:
                        texts.append(turn.text)
                    if turn.kind != "normal":
                        break
                    state_now = turn.state
                    continue
                last_loc = state_now.loc
                for _ in range(15):                       # hard safety cap
                    sent.append(rep_cmd)
                    turn = engine.step(rep_cmd)
                    if turn.kind != "normal":
                        break
                    state_now = turn.state
                    if turn.state.loc == last_loc:        # move stalled -> stop (free)
                        break
                    last_loc = turn.state.loc
                    stop, _why = judge_loop_stop(llm, goal, turn.text)  # LLM judges
                    if stop:
                        break
                if turn is not None and turn.text:
                    texts.append(turn.text)               # narrate where we ended
                if turn is not None and turn.kind != "normal":
                    break
                continue
            sent.append(cmd)
            turn = engine.step(cmd)
            if turn.text:
                texts.append(turn.text)
            if turn.kind != "normal":
                break
            state_now = turn.state

        combined = "\n".join(texts + info)
        if turn is None:                          # only info / no-op commands
            turn = Turn("normal", combined or "(nothing happens)", state=state_now)
        else:
            turn.text = combined
        emit_raw(sent, turn.text)
        process(turn, parse, prev, sent)
        record(line, turn.text)

    while not ended:
        try:
            line = input_fn().strip()
        except (EOFError, StopIteration):
            break
        if not line:
            continue

        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            arg = arg.strip()
            if cmd == "quit":
                break
            elif cmd == "help":
                output_fn(_HELP)
            elif cmd == "report":
                snap = diag_state["snapshot"]
                zh = settings.language == "zh"
                if not snap:
                    output_fn("目前没有可上报的错误。" if zh
                              else "No recent error to report.")
                else:
                    path, text = snap
                    title = "[bug] " + " ".join(text.split())[:70]
                    url = diag.issue_url(title, text)
                    output_fn(("打开下面的链接即可提交（提交前请自行检查内容）：\n" if zh
                               else "Open this link to file the report (review it first):\n")
                              + url
                              + (f"\n（完整快照：{path}）" if zh else f"\n(full snapshot: {path})"))
                    try:
                        import webbrowser
                        webbrowser.open(url)
                    except Exception:
                        pass
            elif cmd == "guide":
                output_fn(guide(settings.language))
            elif cmd == "lang":
                settings.language = arg or settings.language
                persist_config()
                output_fn(f"[language = {settings.language}]")
            elif cmd == "config":
                field, _, val = arg.partition(" ")
                field, val = field.strip().lower(), val.strip()
                if not field:
                    key = settings.api_key or ""
                    masked = (key[:3] + "…" + key[-2:]) if len(key) > 6 else (
                        "(set)" if key else "(none)")
                    output_fn(f"[config] model={settings.model or '(unset)'}  "
                              f"base={settings.base_url or '(unset)'}  key={masked}  "
                              f"lang={settings.language}")
                    output_fn("  change: /config model <name> | base <url> | "
                              "key <key> | lang <en|zh>")
                elif not val:
                    output_fn("  usage: /config <model|base|key|lang> <value>")
                else:
                    known = True
                    if field == "model":
                        settings.model = val
                    elif field in ("base", "base_url", "url"):
                        settings.base_url = val
                    elif field in ("key", "api_key", "apikey"):
                        settings.api_key = val
                    elif field in ("lang", "language"):
                        settings.language = val
                    else:
                        known = False
                        output_fn("  unknown field; use model|base|key|lang")
                    if known:
                        if hasattr(llm, "reconfigure"):
                            try:
                                llm.reconfigure(settings.base_url, settings.api_key,
                                                settings.model)
                            except Exception as exc:        # pragma: no cover
                                output_fn(f"  [warn] {exc}")
                        persist_config()
                        output_fn(f"  [saved: {field}]")
            elif cmd == "hints":
                hints.enabled = arg == "on"
                output_fn(f"[hints = {'on' if hints.enabled else 'off'}]")
            elif cmd == "raw":
                settings.show_raw = arg == "on"
                output_fn(f"[raw = {'on' if settings.show_raw else 'off'}]")
            elif cmd == "purist":
                on = arg == "on"
                settings.multi_step = not on
                settings.auto_advance = not on
                if on:
                    hints.enabled = False
                output_fn(f"[purist = on]  faithful to the 1977 original: only "
                          "translation + narration, one action per turn"
                          if on else
                          "[purist = off]  modern conveniences re-enabled")
            elif cmd == "multistep":
                settings.multi_step = arg == "on"
                output_fn(f"[multi-step = {'on' if settings.multi_step else 'off'}]")
            elif cmd == "autoadvance":
                settings.auto_advance = arg == "on"
                output_fn(f"[auto-advance = {'on' if settings.auto_advance else 'off'}]")
            elif cmd == "hint":
                output_fn(hints.maybe_hint(llm, current, vocab, settings.language,
                          explicit=True) or "[no hint]")
            elif cmd == "save" and saves:
                zh = settings.language == "zh"
                if not arg:
                    output_fn("用法：/save <名字>" if zh else "usage: /save <name>")
                elif arg in saves.list() and not confirm(
                        f"已存在存档 '{arg}'，覆盖吗？(y/n)" if zh
                        else f"A save named '{arg}' already exists. Overwrite? (y/n)"):
                    output_fn("[已取消，未覆盖]" if zh else "[cancelled — not overwritten]")
                else:
                    saves.save(arg, settings.autosave_path)
                    output_fn(f"[saved '{arg}']")
            elif cmd == "load" and saves and engine_factory:
                if arg not in saves.list():                  # validate BEFORE closing
                    output_fn(f"[no save named '{arg}']")
                    continue
                engine.close()                              # close FIRST
                saves.load(arg, settings.autosave_path)      # THEN copy slot
                engine = engine_factory()
                lt = engine.start(fresh=False)               # resume, no reseed
                output_fn(lt.text)
                if lt.kind == "ended":
                    ended = True
                    continue
                current = lt.state
                hints.observe(current)
                pending_ask = None
                output_fn(f"[loaded '{arg}']")
            elif cmd == "new" and engine_factory:
                engine.close()                              # discard current game
                try:
                    os.remove(settings.autosave_path)
                except OSError:
                    pass
                engine = engine_factory()
                nt = engine.start(fresh=True)
                if nt.kind == "ended":
                    ended = True
                    output_fn(nt.text)
                    continue
                current = nt.state
                hints.observe(current)
                history.clear()
                pending_ask = None
                output_fn("[new game]")
                present_intro(nt)
            else:
                output_fn(_HELP)
            continue

        prev = current
        diag_state["line"] = line
        try:
            run_turn(line, prev)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            # A transient LLM/network error must NOT end the game. Snapshot it,
            # tell the player what to check, and carry on.
            if notify_fn:
                notify_fn(None)
            short = " ".join(str(exc).split())[:200]
            path = take_snapshot("llm-error", short, traceback.format_exc())
            if settings.language == "zh":
                output_fn("⚠️ 这一轮与模型通信出错（游戏没中断，可重试或换模型）：\n  " + short
                          + "\n请检查你的 LLM 端点/密钥是否有效（用 /config 查看）。"
                          + (f"\n错误快照已存：{path}。" if path else "")
                          + " 用 /report 可一键生成上报链接。")
            else:
                output_fn("⚠️ Trouble talking to the model this turn (the game is still "
                          "running — retry or /config another model):\n  " + short
                          + "\nCheck your LLM endpoint/key (see /config)."
                          + (f"\nError snapshot saved: {path}." if path else "")
                          + " Use /report to file a bug.")

    engine.close()
