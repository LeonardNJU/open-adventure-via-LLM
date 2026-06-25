# SPDX-FileCopyrightText: (C) 2026 Leonard Li and CaveBridge contributors
# SPDX-License-Identifier: BSD-2-Clause
from cavebridge.llm import FakeLLM
from cavebridge.state import GameState, ObjectRef
from cavebridge.vocab import Vocab
from cavebridge.settings import Settings
from cavebridge.saves import SaveStore
from cavebridge.engine import Turn
from cavebridge.repl import run_repl


class StubEngine:
    def __init__(self):
        self.sent = []
        self._st = GameState(turns=0, loc=1, loc_name="road", dark=False)

    def start(self, fresh):
        return Turn("normal", "intro", state=self._st)

    def state(self):
        return self._st

    def step(self, cmd):
        self.sent.append(cmd)
        self._st = GameState(turns=1, loc=3, loc_name="inside building",
                             dark=False, inventory=[ObjectRef(2, "lamp", 0)])
        return Turn("normal", "OK", state=self._st)

    def answer(self, yes):
        return Turn("normal", "done", state=self._st)

    def close(self):
        return None


def test_turn_parses_steps_narrates():
    llm = FakeLLM(['{"command": "take lamp"}', "你拿起了灯。"])
    eng = StubEngine()
    out = []
    inputs = iter(["拿灯", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm,
             vocab=Vocab([], ["lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=out.append)
    assert eng.sent == ["take lamp"]
    assert any("你拿起了灯" in s for s in out)


def test_multi_step_executes_all_commands():
    # one player line -> multiple canonical commands, executed in order
    llm = FakeLLM(['{"commands": ["take keys", "take lamp"]}', "你拿起了钥匙和灯。"])
    eng = StubEngine()
    out = []
    inputs = iter(["都拿了", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm,
             vocab=Vocab([], ["keys", "lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=out.append)
    assert eng.sent == ["take keys", "take lamp"]
    assert any("钥匙和灯" in s for s in out)


def test_takeall_expands_using_current_visible_state():
    class Stub(StubEngine):
        def __init__(self):
            super().__init__()
            self._st = GameState(turns=0, loc=3, loc_name="inside", dark=False,
                                 visible=[ObjectRef(1, "keys"), ObjectRef(2, "lamp")])

        def step(self, cmd):                         # keep state stable across takes
            self.sent.append(cmd)
            return Turn("normal", "OK", state=self._st)

    eng = Stub()
    llm = FakeLLM(['{"commands": ["@takeall"]}', "拿好了。"])
    inputs = iter(["都拿了", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm,
             vocab=Vocab([], ["keys", "lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None)
    assert eng.sent == ["take keys", "take lamp"]


def test_repeat_advances_until_target():
    class Walker(StubEngine):
        def __init__(self):
            super().__init__()
            self._i = 0
            self._scenes = [("valley", "You are in a valley beside a stream."),
                            ("slit", "Water splashes into a slit in the rock."),
                            ("grate", "You're in a depression with a steel grate.")]
            self._st = GameState(turns=0, loc=10, loc_name="valley", dark=False)

        def step(self, cmd):
            self.sent.append(cmd)
            loc, text = self._scenes[min(self._i, len(self._scenes) - 1)]
            self._i += 1
            self._st = GameState(turns=self._i, loc=10 + self._i, loc_name=loc, dark=False)
            return Turn("normal", text, state=self._st)

    eng = Walker()
    # parse -> then the LLM judges stop after each step (false, false, true) -> narrate
    llm = FakeLLM(['{"commands": ["@repeat:downstream:reach the grate"]}',
                   '{"stop": false}', '{"stop": false}', '{"stop": true}',
                   "你顺流而下，来到栅栏前。"])
    inputs = iter(["顺着小溪走到栅栏", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm, vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None)
    assert eng.sent == ["downstream", "downstream", "downstream"]   # LLM stopped at grate


def test_exits_query_answered_without_engine_call():
    class Stub(StubEngine):
        def __init__(self):
            super().__init__()
            self._st = GameState(turns=0, loc=1, loc_name="road", dark=False,
                                 exits=["north", "south", "in"])

    eng = Stub()
    llm = FakeLLM(['{"commands": ["@exits"]}', "你可以往北、南走，或进屋。"])
    out = []
    inputs = iter(["有哪些出口", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm, vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=out.append)
    assert eng.sent == []                            # no engine command issued
    assert any("北" in s for s in out)


def test_save_intent_uses_frontend_not_engine(tmp_path):
    s = Settings(autosave_path=str(tmp_path / "live.adv"))
    open(s.autosave_path, "wb").write(b"LIVE")
    store = SaveStore(str(tmp_path / "slots"))
    eng = StubEngine()
    llm = FakeLLM(['{"commands": ["@save"]}', "已为你存档。"])
    inputs = iter(["存档", "/quit"])
    run_repl(settings=s, engine=eng, llm=llm, vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None, saves=store)
    assert eng.sent == []                  # never sends the engine's disabled 'save'
    assert "quick" in store.list()         # front-end quick slot written


def test_raw_view_shows_command_and_engine_text():
    llm = FakeLLM(['{"command": "take lamp"}', "你拿起了灯。"])
    eng = StubEngine()
    out = []
    inputs = iter(["拿灯", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm,
             vocab=Vocab([], ["lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=out.append)
    joined = "\n".join(out)
    assert "⟦cmd⟧" in joined and "take lamp" in joined
    assert "⟦raw⟧" in joined and "OK" in joined        # StubEngine.step returns "OK"


def test_raw_off_suppresses_view():
    llm = FakeLLM(['{"command": "take lamp"}', "你拿起了灯。"])
    eng = StubEngine()
    out = []
    inputs = iter(["/raw off", "拿灯", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm,
             vocab=Vocab([], ["lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=out.append)
    assert "⟦cmd⟧" not in "\n".join(out)


def test_streaming_narration_goes_through_stream_fn():
    # parse via complete (json), narration via stream -> stream_fn gets chunks
    llm = FakeLLM(['{"command": "take lamp"}', "你拿起了灯。"])
    chunks = []
    inputs = iter(["拿灯", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=StubEngine(), llm=llm,
             vocab=Vocab([], ["lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None,
             stream_fn=chunks.append)
    assert "你拿起了灯。" in "".join(chunks)


class FakeTTY:
    """Minimal terminal emulator: applies \\r and the CSI 'K' (clear-to-EOL)
    escape so we can assert what a real terminal would actually still show."""

    def __init__(self):
        self.line: list[str] = []
        self.cur = 0
        self.committed: list[str] = []

    def write(self, s: str) -> None:
        i = 0
        while i < len(s):
            c = s[i]
            if c == "\x1b" and i + 1 < len(s) and s[i + 1] == "[":
                j = i + 2
                while j < len(s) and not s[j].isalpha():
                    j += 1
                if j < len(s) and s[j] == "K":          # clear cursor..EOL
                    del self.line[self.cur:]
                i = j + 1
                continue
            if c == "\r":
                self.cur = 0
            elif c == "\n":
                self.committed.append("".join(self.line))
                self.line, self.cur = [], 0
            else:
                if self.cur < len(self.line):
                    self.line[self.cur] = c
                else:
                    self.line.append(c)
                self.cur += 1
            i += 1

    def text(self) -> str:
        return "\n".join(self.committed + ["".join(self.line)])


def test_thinking_indicator_does_not_erase_narration():
    # Regression: the "DM is writing…" placeholder must not wipe the narration's
    # last line when chunks have already streamed.
    tty = FakeTTY()
    llm = FakeLLM(['{"command": "take lamp"}', "你拿起了灯。"])
    inputs = iter(["拿灯", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=StubEngine(), llm=llm,
             vocab=Vocab([], ["lamp"], ["take"]),
             input_fn=lambda: next(inputs),
             output_fn=lambda line: tty.write(line + "\n"),
             stream_fn=tty.write,
             notify_fn=lambda m: tty.write("\r\x1b[K" + (m or "")))
    rendered = tty.text()
    assert "你拿起了灯。" in rendered          # narration survived
    assert "正在输入" not in rendered          # placeholder fully cleared


def test_intro_narrated_when_enabled():
    eng = StubEngine()
    llm = FakeLLM(["欢迎来到巨洞冒险。你站在路的尽头，面前是一座小砖屋。"])
    out = []
    inputs = iter(["/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm, vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=out.append, narrate_intro=True)
    assert any("欢迎" in s for s in out)


def test_new_command_starts_fresh(tmp_path):
    s = Settings(autosave_path=str(tmp_path / "live.adv"))
    open(s.autosave_path, "wb").write(b"OLD")
    made = {"n": 0}

    def factory():
        made["n"] += 1
        return StubEngine()

    inputs = iter(["/new", "/quit"])
    run_repl(settings=s, engine=StubEngine(), llm=FakeLLM([]), vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None,
             engine_factory=factory)
    assert made["n"] == 1                          # /new rebuilt the engine
    assert not (tmp_path / "live.adv").exists()    # old save discarded


def test_resume_uses_no_reseed_path():
    # resume=True must not crash and not call the LLM for a no-narrate intro
    run_repl(settings=Settings(), engine=StubEngine(), llm=FakeLLM([]),
             vocab=Vocab([], [], []), input_fn=lambda: next(iter(["/quit"])),
             output_fn=lambda _l: None, resume=True)


def test_quit_uses_no_llm():
    eng = StubEngine()
    run_repl(settings=Settings(), engine=eng, llm=FakeLLM([]), vocab=Vocab([], [], []),
             input_fn=lambda: next(iter(["/quit"])), output_fn=lambda _l: None)
    assert eng.sent == []


def test_save_then_load_order(tmp_path):
    s = Settings(autosave_path=str(tmp_path / "live.adv"))
    open(s.autosave_path, "wb").write(b"LIVE")
    order = []

    class RecordingStore(SaveStore):
        def load(self, name, live):
            order.append("copy")
            super().load(name, live)

    store = RecordingStore(str(tmp_path / "slots"))

    class CloseTrackingStub(StubEngine):
        def close(self):
            order.append("close")
            open(s.autosave_path, "wb").write(b"CURRENT")  # engine autosave-on-close
            return None

    def factory():
        order.append("spawn")
        return CloseTrackingStub()

    inputs = iter(["/save cp", "/load cp", "/quit"])
    run_repl(settings=s, engine=CloseTrackingStub(), llm=FakeLLM([]),
             vocab=Vocab([], [], []), input_fn=lambda: next(inputs),
             output_fn=lambda _l: None, saves=store, engine_factory=factory)
    # /load order proves close happens BEFORE the slot copy, then spawn:
    assert order == ["close", "copy", "spawn", "close"]
    # and the saved slot still holds the pre-load state (b"LIVE"):
    assert open(store._path("cp"), "rb").read() == b"LIVE"


def test_load_missing_slot_keeps_engine_open(tmp_path):
    s = Settings(autosave_path=str(tmp_path / "live.adv"))
    open(s.autosave_path, "wb").write(b"LIVE")
    store = SaveStore(str(tmp_path / "slots"))
    eng = StubEngine()
    closes = []
    eng.close = lambda: closes.append(1)        # type: ignore[method-assign]
    inputs = iter(["/load nope", "/quit"])
    run_repl(settings=s, engine=eng, llm=FakeLLM([]), vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None,
             saves=store, engine_factory=lambda: StubEngine())
    assert closes == [1]                         # only the final /quit close


def test_executed_commands_and_delta_reach_narrator():
    # Regression for "OK OK OK" → real feedback: the narrator must be told what
    # the player actually did and how the inventory changed.
    llm = FakeLLM(['{"command": "take lamp"}', "你拿起了灯。"])
    eng = StubEngine()
    inputs = iter(["拿灯", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=eng, llm=llm,
             vocab=Vocab([], ["lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None)
    narration = llm.calls[1]["messages"][-1]["content"]      # call 0 is the parse
    assert "take lamp" in narration                          # executed action
    assert "now carrying: lamp" in narration                 # state delta


def test_delta_reports_move_from_and_to():
    # Regression: a move must read as from->to so a teleport isn't narrated as "still here".
    from cavebridge.repl import _delta
    a = GameState(turns=0, loc=5, loc_name="Debris Room", dark=False)
    b = GameState(turns=1, loc=3, loc_name="Inside Building", dark=False)
    d = _delta(a, b) or ""
    assert "Debris Room" in d and "Inside Building" in d and "moved from" in d


def test_empty_narration_retries_then_shows_something():
    # The streamed narration comes back empty -> retry non-streaming; that text
    # must still reach the player (no silent turn).
    llm = FakeLLM(['{"command": "look"}', "", "（回退）你环顾四周。"])
    chunks = []
    inputs = iter(["看看", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=StubEngine(), llm=llm,
             vocab=Vocab([], [], ["look"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None,
             stream_fn=chunks.append)
    assert "回退" in "".join(chunks)


def test_empty_narration_last_resort_shows_engine_text():
    # Stream empty AND the retry empty -> fall back to the engine's own text.
    llm = FakeLLM(['{"command": "look"}', "", ""])
    chunks = []
    inputs = iter(["看看", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=StubEngine(), llm=llm,
             vocab=Vocab([], [], ["look"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None,
             stream_fn=chunks.append)
    assert "OK" in "".join(chunks)        # StubEngine.step returns "OK"


class _BoomLLM(FakeLLM):
    def complete(self, *a, **k):
        raise RuntimeError("503 high demand")

    def stream(self, *a, **k):
        raise RuntimeError("503 high demand")
        yield  # pragma: no cover


def test_llm_error_keeps_repl_alive_and_snapshots(tmp_path):
    from cavebridge.config import config_path
    out = []
    inputs = iter(["看看周围", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=StubEngine(), llm=_BoomLLM([]),
             vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=out.append,
             config_path=config_path(str(tmp_path)))
    joined = "\n".join(out)
    assert "出错" in joined                          # friendly error, not a crash
    import os
    errs = os.path.join(str(tmp_path), "errors")     # a snapshot was written
    assert os.path.isdir(errs) and os.listdir(errs)


def test_report_command_builds_issue_url(tmp_path, monkeypatch):
    import webbrowser
    from cavebridge.config import config_path
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)   # don't open a browser
    out = []
    inputs = iter(["看看", "/report", "/quit"])
    run_repl(settings=Settings(language="zh"), engine=StubEngine(), llm=_BoomLLM([]),
             vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=out.append,
             config_path=config_path(str(tmp_path)))
    assert any("github.com" in s and "issues/new" in s for s in out)


def test_purist_caps_to_one_action():
    eng = StubEngine()
    llm = FakeLLM(['{"commands": ["take keys", "take lamp"]}', "好的。"])
    inputs = iter(["都拿了", "/quit"])
    run_repl(settings=Settings(language="zh", multi_step=False, auto_advance=False),
             engine=eng, llm=llm, vocab=Vocab([], ["keys", "lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None)
    assert eng.sent == ["take keys"]                         # only the first action


def test_purist_takeall_takes_a_single_item():
    class Stub(StubEngine):
        def __init__(self):
            super().__init__()
            self._st = GameState(turns=0, loc=3, loc_name="inside", dark=False,
                                 visible=[ObjectRef(1, "keys"), ObjectRef(2, "lamp")])

        def step(self, cmd):
            self.sent.append(cmd)
            return Turn("normal", "OK", state=self._st)

    eng = Stub()
    llm = FakeLLM(['{"commands": ["@takeall"]}', "好的。"])
    inputs = iter(["都拿了", "/quit"])
    run_repl(settings=Settings(language="zh", multi_step=False),
             engine=eng, llm=llm, vocab=Vocab([], ["keys", "lamp"], ["take"]),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None)
    assert eng.sent == ["take keys"]                         # not a batch


def test_purist_repeat_is_a_single_step_no_judge():
    eng = StubEngine()
    llm = FakeLLM(['{"commands": ["@repeat:north:go far"]}', "好的。"])
    inputs = iter(["一直往北走", "/quit"])
    run_repl(settings=Settings(language="zh", auto_advance=False),
             engine=eng, llm=llm, vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None)
    assert eng.sent == ["north"]                             # one step, no loop
    assert len(llm.calls) == 2                               # parse + narrate, no judge


def test_config_command_updates_and_persists(tmp_path):
    from cavebridge.config import config_path, load_config

    s = Settings(language="zh")
    cfg = config_path(str(tmp_path))
    inputs = iter(["/config model qwen3", "/quit"])
    run_repl(settings=s, engine=StubEngine(), llm=FakeLLM([]), vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None, config_path=cfg)
    assert s.model == "qwen3"
    assert load_config(cfg).get("model") == "qwen3"


def test_lang_command_persists_language(tmp_path):
    from cavebridge.config import config_path, load_config

    s = Settings(language="zh")
    cfg = config_path(str(tmp_path))
    inputs = iter(["/lang en", "/quit"])
    run_repl(settings=s, engine=StubEngine(), llm=FakeLLM([]), vocab=Vocab([], [], []),
             input_fn=lambda: next(inputs), output_fn=lambda _l: None, config_path=cfg)
    assert s.language == "en"
    assert load_config(cfg).get("language") == "en"
