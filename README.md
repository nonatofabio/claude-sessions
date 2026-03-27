<p align="center">
  <img src="assets/logo.svg" width="128" alt="claude-sessions logo"/>
</p>

<h1 align="center">claude-sessions</h1>

<p align="center">
  <strong>A terminal UI for browsing, searching, and resuming your Claude Code sessions.</strong>
</p>

<p align="center">
  <a href="#install">Install</a> &middot;
  <a href="#usage">Usage</a> &middot;
  <a href="#controls">Controls</a> &middot;
  <a href="#features">Features</a> &middot;
  <a href="LICENSE">MIT License</a>
</p>

---

<p align="center">
  <img src="assets/demo.gif" alt="claude-sessions demo" width="100%"/>
</p>

---

Ever wonder what you worked on three days ago? Or want to pick up exactly where you left off in a session from last week?

**claude-sessions** scans all your Claude Code transcripts and gives you a fast, keyboard-driven terminal UI to browse, search, and jump back into any session.

## Install

```bash
# With uv (recommended)
uv tool install claude-sessions

# With semantic search (lightweight 29MB model, finds "auth" when you search "login")
uv tool install "claude-sessions[semantic]"

# With pip
pip install claude-sessions            # basic
pip install "claude-sessions[semantic]" # + semantic search

# From source
git clone https://github.com/nonatofabio/claude-sessions.git
cd claude-sessions
uv tool install -e ".[semantic]"
```

Then just:

```bash
claude-sessions
```

## Usage

```
claude-sessions            # launch the TUI
claude-sessions --refresh  # force re-scan all sessions (rebuilds cache)
claude-sessions --no-active  # skip active session detection
claude-sessions --help     # show all options
```

On first run, it scans `~/.claude/projects/` and builds a JSON cache. First scan takes ~1s depending on how many sessions you have. Subsequent launches load from cache in ~30ms.

## Controls

Left hand on **WASD**, right hand on **arrow keys**. Like a game.

| Key | Action |
|-----|--------|
| **W / S** | Navigate up/down in the session list |
| **A / D** | Collapse/expand group sections |
| **Arrow keys** | Scroll the detail pane |
| **o** or **Enter** | Open session in a new terminal (`claude --resume`) |
| **/** | Search — type to filter, **Enter** to commit, **Esc** to clear |
| **1 – 5** | Group by: Project / Topic / Domain / Date / Branch |
| **r** | Refresh (re-scan sessions + detect active) |
| **q** | Quit |

## Features

### Multi-dimensional grouping

Switch how sessions are organized with a single keypress:

- **1 — Project**: Group by working directory (e.g., `dev/myapp`, `docs/specs`)
- **2 — Topic**: Auto-tagged from content (e.g., `agents`, `trust-verification`, `experimentation`)
- **3 — Domain**: What kind of work (e.g., `coding`, `research`, `writing`, `ops`)
- **4 — Date**: By calendar day
- **5 — Branch**: By git branch active during the session

### Session detail pane

Each session shows:
- **Auto-generated name** from the first prompt
- **Metadata**: project, git branch, model, duration, Claude Code version, permission mode, working directory
- **Stats**: prompt count, tool calls, entries, subagent count, token usage
- **Trust signals**: approvals (green) vs. corrections (red) vs. neutral — see at a glance how collaborative a session was
- **Tags**: topics, domains, and top tools used
- **Full prompt history** with color-coded borders (green = approval, red = correction)

### Cross-platform support

Works on **macOS**, **Linux**, and **Windows**:

| | macOS | Linux | Windows |
|---|---|---|---|
| **Browse & search** | Yes | Yes | Yes |
| **Open session** | Terminal.app (AppleScript) | Auto-detects: gnome-terminal, konsole, alacritty, kitty, wezterm, xterm (or `$TERMINAL`) | Windows Terminal or cmd.exe |
| **Active detection** | IDE locks + `pgrep` | IDE locks + `pgrep` | IDE locks + `tasklist` |

### Active session detection

Sessions currently running (in Terminal or IDE) show a green dot. Detection works via:
- IDE lock files (`~/.claude/ide/*.lock`)
- Process inspection (`pgrep` on macOS/Linux, `tasklist` on Windows)

### Hybrid search (BM25 + semantic)

Press `/` and type — results are **ranked by relevance**, not just filtered.

- **BM25 keyword ranking** (always on): handles partial matches, multi-word queries, term importance weighting
- **Semantic search** (with `[semantic]` extra): uses a tiny 29MB embedding model ([model2vec/potion-base-8M](https://huggingface.co/minishlab/potion-base-8M)) to understand meaning. Search "auth problems" and find sessions about "JWT refactoring" — no keyword overlap needed

Semantic embeddings are pre-computed in the background on startup. First run downloads the model (~29MB), then it's cached locally. Search queries take <1ms.

Press **Enter** to lock in the filter and navigate results, **Esc** to reset.

### Resume any session

Press **`o`** on any session to open a new terminal window that runs `claude --resume <session_id>` in the correct working directory. Pick up right where you left off.

### Fast startup

An incremental JSON cache tracks file sizes and modification times. Only changed or new sessions are re-parsed on launch. Typical cached startup: **~30ms**.

## How it works

Claude Code stores conversation transcripts as JSONL files in `~/.claude/projects/`. Each line is a timestamped message (user, assistant, or tool result) with metadata like model, git branch, working directory, and token usage.

**claude-sessions** parses these transcripts and extracts:
- Human prompts (filtering out system messages and tool results)
- Tool usage profiles
- Topic and domain classification via regex pattern matching
- Trust signals (corrections vs. approvals) from prompt language
- File types touched during the session

All extracted metadata is cached in `~/.claude/sessions_tui_cache.json` for fast subsequent loads.

## Requirements

- Python 3.11+
- Claude Code (with sessions in `~/.claude/projects/`)
- macOS, Linux, or Windows

## Tech stack

- [Textual](https://textual.textualize.io/) — terminal UI framework
- [Rich](https://rich.readthedocs.io/) — text formatting (bundled with Textual)
- Standard library only for parsing (json, re, pathlib, dataclasses)

## License

[MIT](LICENSE)
