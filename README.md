# local-agent

A self-verifying coding agent that runs entirely on-device via [Ollama](https://ollama.com),
built for constrained Apple Silicon (tuned on an 8 GB M3), with optional escalation to
Claude Code when the local model gets stuck.

The design principle: **trust no model.** Every "I'm done" claim — local or frontier —
is independently verified by the harness (syntax-check every file, re-run the tests)
before the run is allowed to succeed.

## Architecture

```
task ──> local model (Ollama, ReAct tool loop)
             │  write / edit / read / search / run_python / run_shell
             │  loop detection + escalating nudges
             ▼
        finish claimed ──> harness re-runs tests independently
             │                   │
             │ rejected          │ verified
             ▼                   ▼
        (fix & retry)          done
             │
             │ run fails (loop abort / silence / max steps)
             ▼
        --escalate: hand task + failure to Claude Code CLI
        (workspace-scoped, tool-allowlisted, verified the same way)
```

## Quick start

```bash
./bootstrap.sh                                  # installs Ollama, pulls models, deps
python3 local_agent.py "write and test a fizzbuzz"
python3 local_agent.py --escalate "harder task" # speed tier + Claude Code safety net
python3 local_agent.py                          # interactive REPL
```

For reliable escalation, mint a long-lived token once (`claude setup-token`) and export
it as `CLAUDE_CODE_OAUTH_TOKEN` in `~/.zshenv`. The agent will also find it there itself.

## Model tiers (benchmarked 2026-07-06, 8 GB M3)

| Tier | Model | Loaded size | Role |
|---|---|---|---|
| Speed | `qwen3.5:2b-q4_K_M` | 1.6 GB | auto-picked with `--escalate`; 42+ tok/s |
| Quality | `qwen2.5-coder:7b` | ~5 GB | default without escalation; best when the Mac is idle |
| Mid | `qwen3.5:4b` | ~4 GB | fallback; degrades least under RAM pressure |

Measured result that justifies the speed tier: **2b + escalation reached a
verified-correct state in 2:45 where the 4b alone took 14:18** — the local model
only has to be good enough often enough, because failures are caught and fixed.

Run Ollama with `OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0` (bootstrap does)
to halve the context window's memory cost.

## Harness features

- **Independent finish verification** — the model's success claim is never trusted;
  pytest (or direct test execution) must pass in a subprocess the model doesn't control.
- **Loop detection** — repeated identical tool calls or long failure streaks trigger a
  "form a new hypothesis" nudge, then a clean abort with a transcript pointer.
- **`edit_file`** — exact-snippet replacement so small fixes don't require whole-file
  rewrites (the main fuel of small-model thrash loops).
- **Context trimming** — old tool results are elided to keep the KV cache off swap.
- **Escalation** (`--escalate` / `LOCAL_AGENT_ESCALATE=1`) — failed runs hand off to
  Claude Code, sandboxed to the workspace with a tight tool allowlist.
- **Run transcripts** — every run logs to `.runs/*.jsonl` for postmortems.
- **Live tok/s** per step, so swap-induced slowdowns are visible as they happen.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `LOCAL_AGENT_MODEL` | auto | Ollama model override |
| `LOCAL_AGENT_CTX` | 8192 | context window (16K+ swaps on 8 GB) |
| `LOCAL_AGENT_MAX_STEPS` | 25 | step budget per run |
| `LOCAL_AGENT_ESCALATE` | off | escalate failures to Claude Code |
| `LOCAL_AGENT_TIMEOUT` | 60 | seconds per tool call |
| `LOCAL_AGENT_DEBUG` | off | print tool args/results |

All file and shell tools are sandboxed to `./workspace/`.
