<!--
SPDX-FileCopyrightText: (C) 2026 Leonard Li and CaveBridge contributors
SPDX-License-Identifier: BSD-2-Clause
-->

[English](README.md) · **简体中文**

<p align="center">
  <img src="assets/hero.png" width="860"
       alt="CaveBridge —— 给确定性文字冒险世界的自然语言接口">
</p>

# Open Adventure × LLM —— *CaveBridge*

> 用现代 LLM 给 1977 年的经典《巨洞冒险》（Colossal Cave Adventure）套一层"地下城主"
> 前端：自然语言交互、现代化又宽容的体验、用你的语言叙述（你的模型会多少种语言，它就支持
> 多少种）—— 而原版游戏引擎仍是唯一权威。

CaveBridge 封装了 Eric S. Raymond 的 [Open Adventure](README-open-adventure.adoc) C
引擎，并**不**重写游戏。一个 LLM 守在未改动的引擎前面，只做两件事：

1. **理解** —— 把你的自由文本（"拿起灯并点亮它""都拿了""顺着小溪一直走到栅栏"）翻译成
   引擎的规范指令。
2. **叙述** —— 把引擎简短的输出，用温暖的地下城主口吻、以你的语言复述出来。

C 引擎始终是唯一、权威的世界模型。LLM 绝不凭空捏造房间、物品或情节，也绝不改动游戏状态
—— 所以你得到的是完整、确定性的 1977 原版解谜，外加一层 21 世纪的交互界面。本质就是：
**把老引擎升格为可验证的世界模型，把 LLM 降格为语言接口。**

---

## 亮点

- **自然语言输入，怎么说都行** —— 不用学 `动词 名词` 句式，想怎么说就怎么说。
- **用你的语言叙述** —— 英文、中文，或你的模型会的任何语言，游戏中用 `/lang` 随时切换。
  （内置的玩法说明目前提供中英两版。）
- **有据可依，不编造、不剧透** —— 叙述严格绑定引擎输出；提示只在你索取（`/hint`）或
  开启（`/hints on`）时才给。
- **存档零代价** —— 原版存档会*扣分*；这里每回合都免费自动存档，外加具名存档槽
  （`/save`、`/load`）。
- **多步指令** —— "都拿了""先往北再打开栅栏"。
- **自动前进** —— "一直沿下游走，直到看见栅栏"；由 LLM 裁判在达成目标、遇到危险或卡住
  时停下循环。
- **原文视图** —— 用 `/raw` 查看确切的规范指令与引擎原始文本。
- **"DM 正在输入…"** 在模型生成时显示，生成出来即被叙述替换。

### 忠于原味（Purist 模式）

想要不加修饰的 1977 原味？把现代便利功能**关掉**，只保留不改变玩法的部分 —— 自然语言
翻译与 DM 叙述。在原味模式下，你**每回合只能做一个动作**（不批量、不自动行走），也没有
提示，和原版一模一样 —— 只是看得懂、还是你的母语。

```
/purist on          # 游戏内开启，或启动时设置 CAVEBRIDGE_PURIST=1
```

也可以单独切换：`/multistep on|off`、`/autoadvance on|off`、`/hints on|off`。

---

## 实机演示

你只管说话 —— 一句话多步（"拿所有东西，出房间"）、问问能往哪走、顺着小溪一路下游走到
那道上锁的栅栏。`⟦cmd⟧` / `⟦raw⟧` 两行（用 `/raw` 开关）会显示每一回合背后确切的规范
指令和引擎原始输出，毫无隐藏。

<p align="center">
  <img src="assets/screenshot-play.png" width="900"
       alt="自然语言游玩：拿走所有东西、询问出口、顺流走到栅栏">
</p>

开新游戏时会先给一份玩法说明，并由 DM 讲述开场场景：

<p align="center">
  <img src="assets/screenshot-guide.png" width="640"
       alt="启动玩法说明与 DM 讲述的开场场景">
</p>

---

## 快速开始

你需要一个 **OpenAI 兼容**的对话接口 —— 本地的 LM Studio、Ollama、vLLM，或在线服务皆可。
你**不必**设置环境变量：首次运行时 CaveBridge 会询问接口地址、密钥和模型名并记住它们，
之后随时可在游戏内用 `/config` 修改。

> 本地模型小贴士：关闭"思考/推理"模式，回合更跟手。

### 建议模型

任何 OpenAI 兼容的对话模型都能用。以下三个经实测、体验都不错：

| 模型 | 来源 / 费用 | 接口地址（`base`） |
|---|---|---|
| `gemini-3.1-flash-lite` | Google AI Studio —— 有免费额度 | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `deepseek-v4-flash` | DeepSeek API —— 超便宜 | `https://api.deepseek.com/v1` |
| `qwen3.5-9B` | 自部署（LM Studio / Ollama / vLLM） | `http://localhost:1234/v1` |

首次运行时填写、游戏内用 `/config`、或用环境变量都行。以 Google 免费的 Gemini 为例：

```bash
export OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
export OPENAI_API_KEY="<你的 Google AI Studio key>"
export OPENAI_MODEL="gemini-3.1-flash-lite"
```

### 下载预编译版（推荐）

[**Releases**](../../releases) 里附有单文件可执行程序 —— 无需 Python、无需编译器、无需
依赖。下载对应平台的那一个直接运行，首次运行会引导你连接 LLM。

- **Windows** —— 下载 `cavebridge-windows-x86_64.exe`。双击运行（会自动打开一个命令行
  窗口），或在 PowerShell/cmd 中运行。
- **macOS** —— 下载 `cavebridge-macos-arm64.tar.gz`。它是命令行程序，要**在终端里运行、
  不能双击**（双击只会用文本编辑器打开原始文件）。它没有签名，先清一次 Gatekeeper 隔离标记：
  ```bash
  tar xzf cavebridge-macos-arm64.tar.gz
  xattr -dr com.apple.quarantine cavebridge-macos-arm64   # 放行未签名程序
  ./cavebridge-macos-arm64/cavebridge
  ```
- **Linux** —— 下载 `cavebridge-linux-x86_64.tar.gz`，解压后在终端里运行：
  ```bash
  tar xzf cavebridge-linux-x86_64.tar.gz
  ./cavebridge-linux-x86_64/cavebridge
  ```

### 从源码编译（Linux / macOS）

需要 C 工具链 + `libedit`，以及 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
make CFLAGS="-DADVENT_AUTOSAVE"          # 编译前端驱动的引擎
uv venv && uv pip install pyyaml openai
uv run python -m cavebridge             # 首次运行会询问你的 LLM 信息
```

### Docker（任意系统，也适合没有预编译 exe 的 Windows）

```bash
docker build -t cavebridge .
docker run -it --rm \
  -e OPENAI_BASE_URL=http://host.docker.internal:1234/v1 \
  -e OPENAI_API_KEY=lm-studio \
  -e OPENAI_MODEL=qwen/qwen3.5-9b \
  -e CAVEBRIDGE_LANG=zh \
  -v cavebridge-saves:/root/.cavebridge \
  cavebridge
```

`host.docker.internal` 可访问宿主机上的 LLM（原生 Linux Docker 需加
`--add-host=host.docker.internal:host-gateway`）；`-it` 必不可少。

---

## 玩法

用大白话输入你想做的事。启动时你可以选择**继续上次**还是**开新游戏**，新游戏还会提供一份
玩法说明。

| 命令 | 作用 |
|---|---|
| `/guide` | 玩法说明 |
| `/help` | 列出命令 |
| `/config` | 查看 / 修改 LLM 连接（`/config model <名称>`、`base`、`key`、`lang`） |
| `/hint` · `/hints on｜off` | 单条提示 · 卡住时自动提示 |
| `/lang <语言>` | 切换叙述语言（如 `en`、`zh`、`français`…） |
| `/raw on｜off` | 显示/隐藏规范指令与引擎原文 |
| `/purist on｜off` | 忠于原味模式（只保留翻译 + 叙述） |
| `/multistep on｜off` · `/autoadvance on｜off` | 单独开关便利功能 |
| `/save <名称>` · `/load <名称>` | 具名存档槽（不扣分） |
| `/new` · `/quit` | 新游戏 · 退出（进度已自动保存） |

---

## 配置

连接信息的优先级为 **环境变量 → 已保存的配置 → 首次运行向导**，所以下面任意一种都行：

- 直接运行并回答提示（保存到 `~/.cavebridge/config.json`）。
- 之后在游戏内用 `/config` 修改。
- 或者设置环境变量（方便 Docker / 脚本化）：

| 变量 | 默认 | 含义 |
|---|---|---|
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` | — | LLM 接口（覆盖已保存的配置） |
| `CAVEBRIDGE_LANG` | `en` | 叙述语言 —— `en`、`zh`，或你的模型会的任何语言 |
| `CAVEBRIDGE_PURIST` | `0` | `1` = 原味模式（关闭多步 + 自动前进 + 提示） |
| `CAVEBRIDGE_MULTISTEP` | `1` | 一行多个动作 |
| `CAVEBRIDGE_AUTOADVANCE` | `1` | "一直走直到…"的循环 |
| `CAVEBRIDGE_HINTS` | `0` | `1` 启动即开启自动提示 |
| `CAVEBRIDGE_RAW` | `1` | `0` 隐藏原文视图 |
| `CAVEBRIDGE_SEED` | `1` | 随机种子，可复现的对局 |
| `CAVEBRIDGE_SAVE_DIR` | `~/.cavebridge` | 存档/自动存档/配置的存放目录 |

---

## 工作原理

对 C 引擎打了一个**编译期受控**的小补丁（仅在 `-j` 运行标志下生效）使其可被脚本驱动：它会
打印提示哨兵和一行 `@state` JSON 快照，并在每回合自动存档。默认编译下引擎逐字节不变，其
100+ 项回归测试照常通过。Python 前端（`cavebridge/`）通过普通管道驱动引擎，对照游戏真实
词表解析你的意图，再叙述每一次结果。出口、批量指令、循环都依据引擎自身状态推导 ——
绝不靠猜。

---

## 许可与致谢

本项目以 **BSD-2-Clause** 自由开源，与上游 Open Adventure 相同，任何人皆可游玩、修改、再
分发。

- **Colossal Cave Adventure** —— © 1977, 2005 Will Crowther 与 Don Woods（原版游戏）。
- **Open Adventure**（C 引擎，前向移植）—— © Eric S. Raymond
  <esr@thyrsus.com>，BSD-2-Clause。见 [`COPYING`](COPYING) 与上游 README，本仓库保留为
  [`README-open-adventure.adoc`](README-open-adventure.adoc)。
- 部分素材/文档为 CC-BY-4.0 或 MIT-0（见各文件的 `SPDX-License-Identifier` 头）。
- **CaveBridge**（`cavebridge/` LLM 前端）—— © 2026 Leonard Li 与 CaveBridge 贡献者，
  BSD-2-Clause。

原引擎及其所有版权声明均按许可证要求原样保留。
