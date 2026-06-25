# SPDX-FileCopyrightText: (C) 2026 Leonard Li and CaveBridge contributors
# SPDX-License-Identifier: BSD-2-Clause
from __future__ import annotations

import os
import sys

try:
    import readline  # noqa: F401  — gives input() arrow-key editing + history
except ImportError:  # pragma: no cover - not present on some platforms
    pass

try:
    import termios   # to flush type-ahead before each prompt (Unix)
except ImportError:  # pragma: no cover
    termios = None

from cavebridge.config import config_path, load_config, save_config
from cavebridge.engine import Engine
from cavebridge.llm import LLMClient
from cavebridge.saves import SaveStore
from cavebridge.settings import Settings
from cavebridge.vocab import load_exits, load_vocab


def vars_for_config(s: Settings) -> dict:
    return {"base_url": s.base_url, "api_key": s.api_key,
            "model": s.model, "language": s.language}


def _setup_wizard(s: Settings) -> None:
    """First-run prompt for the LLM connection, so players never need env vars."""
    zh = s.language == "zh"
    print()
    print("首次设置 —— 连接你的 LLM（OpenAI 兼容接口）。直接回车用[默认]。" if zh
          else "First-time setup — connect your LLM (OpenAI-compatible). Enter = [default].")

    def ask(en: str, cn: str, default: str | None) -> str | None:
        suffix = f" [{default}]" if default else ""
        try:
            val = input(f"  {(cn if zh else en)}{suffix}: ").strip()
        except EOFError:
            val = ""
        return val or default

    s.base_url = ask("API base URL", "接口地址", s.base_url or "http://localhost:1234/v1")
    s.api_key = ask("API key", "API 密钥", s.api_key or "lm-studio")
    s.model = ask("Model name (e.g. qwen/qwen3.5-9b)",
                  "模型名（如 qwen/qwen3.5-9b）", s.model) or "local-model"
    print("已保存。以后可用游戏内 /config 修改。" if zh
          else "Saved. Change these anytime with /config in-game.")


def main() -> None:
    s = Settings.from_env()
    # stable, per-user save location so progress persists across launches
    save_dir = os.environ.get("CAVEBRIDGE_SAVE_DIR",
                              os.path.expanduser("~/.cavebridge"))
    os.makedirs(save_dir, exist_ok=True)
    s.autosave_path = os.path.join(save_dir, "session.adv")

    # LLM connection: env var > saved config > first-run setup wizard.
    cfg_path = config_path(save_dir)
    cfg = load_config(cfg_path)
    s.base_url = os.environ.get("OPENAI_BASE_URL") or cfg.get("base_url")
    s.api_key = os.environ.get("OPENAI_API_KEY") or cfg.get("api_key")
    s.model = os.environ.get("OPENAI_MODEL") or cfg.get("model")
    s.language = os.environ.get("CAVEBRIDGE_LANG") or cfg.get("language") or "en"
    if not s.base_url or not s.model:
        _setup_wizard(s)
        save_config(cfg_path, vars_for_config(s))
    elif not cfg:                       # seed config from env on first run
        save_config(cfg_path, vars_for_config(s))

    llm = LLMClient(model=s.model, base_url=s.base_url, api_key=s.api_key)
    # Locate the engine binary + data: explicit env override, else search the cwd,
    # the PyInstaller bundle dir (frozen release), then the repo root.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundle = getattr(sys, "_MEIPASS", None)          # set in a PyInstaller onefile
    advent_name = "advent.exe" if os.name == "nt" else "advent"

    def _locate(name: str, override: str | None) -> str:
        if override and os.path.exists(override):
            return override
        for base in (os.getcwd(), bundle, root):
            if base and os.path.exists(os.path.join(base, name)):
                return os.path.join(base, name)
        return os.path.join(root, name)              # best-effort fallback

    yaml_path = _locate("adventure.yaml", os.environ.get("CAVEBRIDGE_YAML"))
    advent_path = _locate(advent_name, os.environ.get("CAVEBRIDGE_ADVENT")
                          or (s.advent_path if s.advent_path != "./advent" else None))
    if not os.path.exists(advent_path):
        # Common when running from a source checkout without building the engine.
        zh = s.language == "zh"
        rel = "https://github.com/LeonardNJU/CaveBridge/releases"
        if zh:
            print(f"\n找不到游戏引擎 `advent`（期望位置：{advent_path}）。\n"
                  "如果你是从源码运行，请先编译引擎：\n"
                  '    make CFLAGS="-DADVENT_AUTOSAVE"\n'
                  f"或直接下载对应平台的预编译版：{rel}\n"
                  "（也可用 CAVEBRIDGE_ADVENT=/path/to/advent 指定路径。）")
        else:
            print(f"\nGame engine `advent` not found (looked for: {advent_path}).\n"
                  "If you're running from source, build it first:\n"
                  '    make CFLAGS="-DADVENT_AUTOSAVE"\n'
                  f"or download a prebuilt binary for your platform: {rel}\n"
                  "(You can also point CAVEBRIDGE_ADVENT=/path/to/advent.)")
        sys.exit(1)
    vocab = load_vocab(yaml_path)
    exits_by_loc = load_exits(yaml_path)
    saves = SaveStore(os.path.join(save_dir, "saves"))

    def factory() -> Engine:
        return Engine(advent_path, seed=s.seed, autosave_path=s.autosave_path,
                      exits_by_loc=exits_by_loc)

    # The player decides: resume the last session, or start a new game.
    resume = False
    if os.path.exists(s.autosave_path):
        zh = s.language == "zh"
        ans = input("发现上次的存档。载入上次进度吗？(y 载入 / n 新游戏): " if zh
                    else "Found a previous save. Resume it? (y = load / n = new): ").strip().lower()
        resume = (ans[:1] in ("y", "1")
                  or any(k in ans for k in ("载", "继续", "上次", "load", "resume")))
        if not resume:
            try:
                os.remove(s.autosave_path)      # discard old save for a clean start
            except OSError:
                pass

    # New game: offer our how-to-play guide (we auto-decline the engine's own
    # instructions, so this is the player's intro to this version).
    if not resume:
        zh = s.language == "zh"
        ans = input("要看玩法说明吗？(y/n): " if zh
                    else "Want a quick how-to-play? (y/n): ").strip().lower()
        if ans[:1] in ("y", "1") or any(k in ans for k in ("要", "好", "看", "yes")):
            from cavebridge.guide import guide
            print(guide(s.language))

    prompt = "\n你> " if s.language == "zh" else "\nyou> "

    def read_input() -> str:
        # discard any type-ahead buffered while the LLM was busy, so it isn't
        # silently submitted with the next line
        if termios is not None:
            try:
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass
        return input(prompt)

    def notify(msg: str | None) -> None:
        # transient "DM is writing…" status line; \r + clear-to-EOL on a TTY only,
        # so it's overwritten by the narration and never pollutes piped output.
        if not sys.stdout.isatty():
            return
        sys.stdout.write("\r\033[K" + (msg or ""))
        sys.stdout.flush()

    from cavebridge.repl import run_repl
    run_repl(settings=s, engine=factory(), llm=llm, vocab=vocab,
             input_fn=read_input,
             output_fn=lambda line: print(line, flush=True),
             stream_fn=lambda chunk: (sys.stdout.write(chunk), sys.stdout.flush()),
             notify_fn=notify, config_path=cfg_path,
             saves=saves, engine_factory=factory, narrate_intro=True, resume=resume)


if __name__ == "__main__":
    main()
