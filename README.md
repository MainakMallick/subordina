<p align="center">
  <img src="assets/logo.svg" alt="Subordina" width="180" height="180">
</p>

<h1 align="center">Subordina</h1>

<p align="center"><em>Rigorous ML research workflows, on the command line.</em></p>


Subordina wraps your research — questions, architecture searches, experiments, paper drafts — in an enforcement-driven agent loop that catches sycophancy, requires cited evidence, and never lets the model declare victory without a verification pass.

v1 ships three commands backed by two skills and a plain-chat fallback. More skills (survey, implementation, revision, manuscript, experiment, analysis, extension) are on the roadmap.

## Requirements

- **Python 3.11+**
- **Claude Code CLI** installed ([install instructions](https://docs.claude.com/en/api/agent-sdk/overview))
- An **Anthropic API key**

## Install

From the repo root:

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Git Bash on Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e .
```

After install, the `subordina` command is on your PATH.

## Configure

Set your API key in the environment (or a `.env` file inside `backend/`):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

With `--runner raw` you don't need a key (mock mode, for development only).

## Quick start

```bash
# 1. Initialize a project in the current folder
cd ~/research/my-project
subordina init .

# 2. Start a chat
subordina chat new --title "TimesNet vs PatchTST"

# 3. Ask a plain question (normal chat, no verification)
subordina say "what's the difference between ETT and ETTh datasets?"

# 4. Run a verified inquiry (2-iteration review loop, cited evidence)
subordina inquiry "Does TimesNet outperform PatchTST on long-horizon forecasting?"

# 5. Run an architecture search (convergence loop)
subordina convergence "best architecture for fault classification from raw ADC radar signals on a 16 GB card"

# 6. See what's been done
subordina history
subordina show <invocation-id>
```

## Commands

| Command | What it does |
|---|---|
| `subordina init [FOLDER]` | Initialize a project; creates `.subordina/state.db` |
| `subordina chat new [--title] [--folder]` | Start a new conversation inside the current project |
| `subordina chat list` | List chats, newest first |
| `subordina chat show <id>` | Chat metadata + invocation count |
| `subordina say "MSG" [--chat ID] [--runner raw\|agent_sdk]` | Plain chat turn — no verification |
| `subordina inquiry "Q" [--chat ID]` | Inquiry skill — verified answer with cited evidence and confidence rating |
| `subordina convergence "problem" [--chat ID]` | Convergence skill — iterated architecture search with 5-axis scoring |
| `subordina history [--chat ID] [--limit N]` | List past invocations |
| `subordina show <id>` | Render a verified artifact (or diagnostic for non-terminal invocations) |

Short IDs are the first 8 characters of a UUID; prefix matching is supported everywhere.

## How skills work

Two skills in v1:

- **Inquiry** (`subordina inquiry`) — answer a research question with structural verification. Claude drafts an answer with cited evidence, then Claude in reviewer mode tears it apart. Rubber-stamp reviews are rejected by a mechanical critique-quality gate (length >= 50 chars, no "looks good", no sycophancy patterns, pass verdicts must cite what was verified). On a failed review, the draft is revised and re-reviewed. After two failures the loop escalates to you with the full critique history.

- **Convergence** (`subordina convergence`) — run an iterated architecture search. Claude proposes candidate methods with 5-axis scores (theoretical, empirical, feasibility, complexity, novelty; weighted 3/3/2/1/1, normalized to 0-100). Each iteration the current leader is challenged with adversarial evidence. A final recommendation can only be recorded after >= 3 iterations AND the leader has survived 2 consecutive challenges.

Plain chat (`subordina say`) is just a normal conversation with Claude — no loop, no verification, no confidence rating. Use it for follow-up questions, context-setting, or anything where the overhead of verification isn't warranted.

## Folders

Every project is bound to a folder. Every chat inherits that folder by default, but you can override with `subordina chat new --folder <path>` if a specific conversation needs its own working directory. Subordina can read and write anywhere inside the chat's folder (via the model's `read_file` / `write_file` tools). It cannot escape that folder — path traversal attempts are rejected.

## What's not in v1

- Monetization / licensing (v1.1)
- Other skills: survey, implementation, revision, manuscript, experiment, analysis, extension (v1.2+)
- Web UI / SaaS (deferred; current mockups are at `docs/superpowers/specs/`)
- GPU experiment execution (lands with the `experiment` skill in v1.5)

## Troubleshooting

**`subordina: command not found`**
You're not in the venv. `source backend/.venv/Scripts/activate` (or the macOS/Linux equivalent).

**`ANTHROPIC_API_KEY is not set`**
Export it in your shell or put it in `backend/.env`. With `--runner raw` you don't need a key (mock mode, for dev only).

**`No Subordina project found`**
Run `subordina init .` in a folder first.

**Real API calls are slow or stuck**
Check that Claude Code CLI is installed and logged in. Check your API key works with `curl`. Use `--runner raw` to verify the CLI wiring independent of the API.

## Running the test suite

```bash
cd backend
source .venv/Scripts/activate
pytest -v -W error
```

Expected: 111 tests pass + 1 integration test skipped (skipped unless `RUN_INTEGRATION=1` and `ANTHROPIC_API_KEY` are both set).

To run the real-API integration test (requires `ANTHROPIC_API_KEY` and costs ~$0.02):

```bash
RUN_INTEGRATION=1 pytest tests/test_runner_agent_sdk.py -v
```

## Development

- Architecture: `docs/superpowers/specs/2026-04-17-subordina-v1-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-17-subordina-v1-backend.md`
- Project state and north star: `CLAUDE.md`

## License

TODO: license to be decided before public release. Proprietary during closed validation; no public redistribution rights are granted in v1.
