#!/usr/bin/env python3
"""
local_agent.py v2 — a self-verifying coding agent that runs entirely on-device
via Ollama. Built for constrained Apple Silicon (tested target: 8 GB M3).

v2 upgrades, each driven by a measured v1 failure:
  - TRUSTED FINISH -> the harness now independently re-runs the workspace tests
    when the model calls `finish`; a false "it works" claim is rejected and the
    model is sent back to fix it. (v1: qwen2.5-coder:7b claimed success while a
    validation bug survived.)
  - LOOP DETECTION -> repeated identical calls and long failure streaks trigger
    an escalating nudge, then a clean abort with diagnostics. (v1:
    qwen2.5-coder:3b burned all 20 steps in a write/run thrash loop.)
  - edit_file      -> exact string replacement, so small fixes don't require
    rewriting whole files (the main fuel of v1's thrash loop).
  - CONTEXT TRIM   -> old tool results are elided as history grows, keeping the
    KV cache small enough to stay off swap on 8 GB.
  - MODEL REGISTRY -> picks the best pulled model automatically (qwen3.5:4b
    preferred as of 2026-07: 97.5% tool-calling pass rate at 3.4 GB, 256K ctx).
  - THINKING MODE  -> --think enables Qwen3-family deliberate reasoning for
    hard tasks; off by default for speed.
  - RUN TRANSCRIPTS-> every run is logged to .runs/*.jsonl for postmortems.
  - TOKEN STATS    -> per-step tok/s so slowdowns (swap) are visible live.

Usage:
  python3 local_agent.py "Write a function that parses ISO dates and unit-test it."
  python3 local_agent.py --model qwen2.5-coder:7b --think "Refactor workspace/app.py"
  python3 local_agent.py            # interactive REPL
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

try:
    import ollama
except ImportError:
    sys.exit("Missing dependency. Run:  pip install ollama")

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(exist_ok=True)
RUNS_DIR = ROOT / ".runs"

# Best-first. First pulled model wins unless --model is given.
# Benchmarked on this 8 GB M3 (2026-07-06): qwen2.5-coder:7b is the strongest
# in practice — qwen3.5:4b leads leaderboards but loads a vision projector,
# runs verbose/slow here, and stalled silently on the hard task.
# RAM upgrade path (researched 2026-07-06): 16 GB -> qwen3-coder-next (80B-A3B,
# ~70% SWE-bench); 24 GB+ -> qwen3.6:27b. DeepSeek V4 / Kimi K2.x / Llama 4 are
# 160 GB-640 GB — server hardware, not "local" in any consumer sense.
PREFERRED_MODELS = [
    "qwen2.5-coder:7b",
    "qwen3.5:4b",
    "qwen2.5-coder:3b",
    "llama3.2:3b",
]

# With escalation on, the economics flip: local failures are cheap (Claude Code
# cleans them up), so speed beats capability. Measured 2026-07-06: 2b+escalate
# reached verified-correct in 2:45 vs 14:18 for 4b solo, at 1.6 GB vs ~4 GB.
SPEED_MODEL = "qwen3.5:2b-q4_K_M"

# 8192 is the sweet spot on 8 GB: 16384 pushed qwen3.5:4b (weights + vision
# projector + KV cache) ~7 GB into swap and step latency went from seconds to minutes.
NUM_CTX = int(os.environ.get("LOCAL_AGENT_CTX", "8192"))
MAX_STEPS = int(os.environ.get("LOCAL_AGENT_MAX_STEPS", "25"))
SHELL_TIMEOUT = int(os.environ.get("LOCAL_AGENT_TIMEOUT", "60"))
KEEP_ALIVE = os.environ.get("LOCAL_AGENT_KEEP_ALIVE", "10m")
TOOL_RESULT_CAP = 6000          # chars of a tool result kept verbatim
TRIM_THRESHOLD = 26             # messages before old tool results get elided
LOOP_NUDGE_AT = 3               # identical calls / consecutive failures -> nudge
LOOP_ABORT_AT = 6               # ... -> abort

SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are a local software engineering agent. You have tools; prefer acting
    with tools over talking.

    Hard rules:
    - You already operate inside the workspace. Use bare relative paths like
      "is_prime.py" — never prefix "workspace/" or "./".
    - SELF-VERIFY: after writing or changing code, run it (run_python or
      run_shell), read the real output, and fix errors you see. Never claim
      something works without a passing tool run.
    - If the task asks for tests, put them in a file named test_<module>.py and
      run it. Cover edge cases and invalid input, not just the happy path.
    - For small fixes to an existing file, use edit_file with an exact snippet —
      do not rewrite the whole file.
    - If the same error appears twice, STOP repeating yourself: re-read the
      full error message, form a different hypothesis, and change approach.
    - When everything passes, call `finish` ONCE with a short summary and the
      exact command + output that proves it. The harness re-runs your tests
      independently — a false claim is rejected.
    - Your FIRST message must start with a one-sentence plan (files you will
      create, how you will verify). After that: act, do not narrate.
    """
)

# --------------------------------------------------------------------------- #
# Tools — each returns a string that goes back to the model as the tool result.
# --------------------------------------------------------------------------- #

def _safe_path(rel: str) -> Path:
    """Resolve a path and refuse anything that escapes the workspace.

    Forgiving: small models often prefix paths with 'workspace/' even though
    they already operate inside it. Strip that so we don't nest workspace/workspace.
    """
    rel = (rel or "").strip().lstrip("/")
    for prefix in ("./workspace/", "workspace/", "./"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    p = (WORKSPACE / rel).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError(f"Path '{rel}' escapes the workspace sandbox.")
    return p


def read_file(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"ERROR: {path} does not exist."
    text = p.read_text(errors="replace")
    if len(text) < 20000:
        # Line numbers make edit_file targets and error tracebacks line up.
        return "\n".join(f"{i+1}| {ln}" for i, ln in enumerate(text.splitlines()))
    return text[:20000] + "\n...[truncated]"


def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Wrote {len(content)} chars to {path}."


def edit_file(path: str, old: str, new: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"ERROR: {path} does not exist. Use write_file to create it."
    text = p.read_text(errors="replace")
    n = text.count(old)
    if n == 0:
        return ("ERROR: snippet not found in file. read_file it and copy the "
                "exact text (whitespace matters). Do not include the 'N| ' "
                "line-number prefixes read_file shows.")
    if n > 1:
        return f"ERROR: snippet appears {n} times; include more surrounding lines to make it unique."
    p.write_text(text.replace(old, new, 1))
    return f"Edited {path} (1 replacement)."


def list_dir(path: str = ".") -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"ERROR: {path} does not exist."
    entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
    return "\n".join(entries) or "(empty)"


def search(pattern: str, path: str = ".") -> str:
    """Literal-text grep across workspace files."""
    p = _safe_path(path)
    hits, files = [], ([p] if p.is_file() else sorted(p.rglob("*")))
    for f in files:
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        try:
            for i, ln in enumerate(f.read_text(errors="replace").splitlines(), 1):
                if pattern in ln:
                    hits.append(f"{f.relative_to(WORKSPACE)}:{i}: {ln.strip()}")
                if len(hits) >= 50:
                    return "\n".join(hits) + "\n...[capped at 50]"
        except OSError:
            continue
    return "\n".join(hits) or f"No matches for '{pattern}'."


def run_python(code: str) -> str:
    """Run a Python snippet inside the workspace and return stdout+stderr.

    Convenience for small models: every .py file already in the workspace is
    auto-imported (star import, guarded), so a snippet like `print(is_prime(97))`
    works without the model having to remember an explicit import line.
    """
    preamble = ["import sys, os", "sys.path.insert(0, os.getcwd())"]
    for f in sorted(WORKSPACE.glob("*.py")):
        if f.stem.isidentifier() and not f.stem.startswith("test_"):
            preamble.append(f"try:\n    from {f.stem} import *\nexcept Exception:\n    pass")
    full = "\n".join(preamble) + "\n" + code
    return _run([sys.executable, "-c", full])


def run_shell(command: str) -> str:
    """Run a shell command inside the workspace (sandboxed to that dir)."""
    return _run(command, shell=True)


def _run(cmd, shell: bool = False) -> str:
    try:
        proc = subprocess.run(
            cmd,
            shell=shell,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        out = out.strip() or "(no output)"
        tag = "OK" if proc.returncode == 0 else f"EXIT {proc.returncode}"
        return f"[{tag}]\n{out[:8000]}"
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {SHELL_TIMEOUT}s."
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"


TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_dir": list_dir,
    "search": search,
    "run_python": run_python,
    "run_shell": run_shell,
}


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", **({"description": v} if v else {})}
                               for k, v in props.items()},
                "required": required,
            },
        },
    }


TOOL_SCHEMAS = [
    _schema("read_file", "Read a workspace file (returns 'N| ' line-numbered text).",
            {"path": ""}, ["path"]),
    _schema("write_file", "Create or fully overwrite a file in the workspace.",
            {"path": "", "content": ""}, ["path", "content"]),
    _schema("edit_file",
            "Replace ONE exact snippet in an existing file. Preferred for small fixes. "
            "'old' must match the file text exactly (no line-number prefixes) and be unique.",
            {"path": "", "old": "exact text currently in the file",
             "new": "replacement text"}, ["path", "old", "new"]),
    _schema("list_dir", "List files/directories in a workspace path.", {"path": ""}, []),
    _schema("search", "Find lines containing a literal string across workspace files.",
            {"pattern": "", "path": ""}, ["pattern"]),
    _schema("run_python",
            "Execute a Python snippet to TEST your code. Functions from non-test files "
            "you wrote (e.g. is_prime) are already imported and callable directly.",
            {"code": ""}, ["code"]),
    _schema("run_shell",
            "Run a shell command in the workspace; returns output. Use for running tests etc.",
            {"command": ""}, ["command"]),
    _schema("finish",
            "Call ONCE when the task is verified done. The harness re-runs the tests "
            "independently before accepting. Ends the run.",
            {"summary": "", "evidence": "command run + its passing output"}, ["summary"]),
]

# --------------------------------------------------------------------------- #
# Independent verification — never trust the model's word for `finish`.
# --------------------------------------------------------------------------- #

def _has_pytest() -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                       capture_output=True, text=True)
    return r.returncode == 0


def independent_verification(task: str) -> str | None:
    """Return None if the workspace passes verification, else a rejection reason."""
    py_files = [f for f in WORKSPACE.rglob("*.py") if "__pycache__" not in f.parts]
    if not py_files:
        return None  # nothing to verify (task may not have been a coding task)

    # 1. Every file must at least be syntactically valid.
    for f in py_files:
        r = subprocess.run([sys.executable, "-m", "py_compile", str(f)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return f"{f.name} has a syntax error:\n{r.stderr.strip()[:1500]}"

    # 2. If test files exist, they must pass.
    test_files = [f for f in py_files
                  if f.name.startswith("test_") or f.stem.endswith("_test")]
    if test_files:
        if _has_pytest():
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "."],
                               capture_output=True, text=True, cwd=WORKSPACE,
                               timeout=SHELL_TIMEOUT)
            if r.returncode != 0:
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                return f"pytest failed:\n{out[:2000]}"
        else:
            for f in test_files:
                r = subprocess.run([sys.executable, str(f)], capture_output=True,
                                   text=True, cwd=WORKSPACE, timeout=SHELL_TIMEOUT)
                if r.returncode != 0:
                    out = ((r.stdout or "") + (r.stderr or "")).strip()
                    return f"{f.name} failed:\n{out[:2000]}"
    elif re.search(r"\btest(s|ed|ing)?\b", task, re.I):
        return ("the task asked for tests, but no test_*.py file exists in the "
                "workspace. Write the tests to a file and run them.")

    return None

# --------------------------------------------------------------------------- #
# Agent loop
# --------------------------------------------------------------------------- #

def extract_text_tool_calls(content: str) -> list[dict]:
    """Fallback for small models that print tool calls as JSON text instead of
    using the native tool-call channel. Finds {...} blobs containing "name" and
    "arguments" and normalizes them to the native tool_calls shape.
    """
    if not content or '"name"' not in content:
        return []
    calls = []
    depth, start = 0, None
    for i, ch in enumerate(content):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blob = content[start : i + 1]
                try:
                    # strict=False: small models put literal newlines inside
                    # JSON strings when printing tool calls as text.
                    obj = json.loads(blob, strict=False)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                    calls.append(
                        {"function": {"name": obj["name"], "arguments": obj["arguments"]}}
                    )
    return calls


def trim_history(messages: list) -> list:
    """Keep the KV cache off swap: elide old tool results once history is long.
    System prompt, task, and the recent tail are always kept verbatim."""
    if len(messages) <= TRIM_THRESHOLD:
        return messages
    head, tail = messages[:2], messages[-14:]
    middle = []
    for m in messages[2:-14]:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
        content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
        if role == "tool" and len(content) > 400:
            m = dict(m) if isinstance(m, dict) else {"role": "tool", "content": content}
            m["content"] = content[:400] + "\n...[old result elided to save context]"
        middle.append(m)
    return head + middle + tail


def chat(model: str, messages: list, think: bool):
    """One model call with thinking-mode support and transient-error retries."""
    kwargs = dict(
        model=model,
        messages=messages,
        tools=TOOL_SCHEMAS,
        options={"num_ctx": NUM_CTX, "temperature": 0.2},
        keep_alive=KEEP_ALIVE,
    )
    for attempt in (1, 2, 3):
        try:
            if think:
                try:
                    return ollama.chat(think=True, **kwargs)
                except (TypeError, ollama.ResponseError):
                    return ollama.chat(**kwargs)  # model/client lacks thinking
            return ollama.chat(**kwargs)
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            print(f"  [retry {attempt}] ollama error: {str(e)[:120]}")
            time.sleep(2 * attempt)


class RunLog:
    def __init__(self) -> None:
        RUNS_DIR.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = RUNS_DIR / f"run-{stamp}.jsonl"

    def write(self, **event) -> None:
        event["t"] = round(time.time(), 2)
        with self.path.open("a") as fh:
            fh.write(json.dumps(event, default=str) + "\n")


def run_agent(task: str, model: str, think: bool = False) -> str:
    log = RunLog()
    log.write(kind="start", task=task, model=model, think=think, ctx=NUM_CTX)
    messages: list = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    call_sigs: list[str] = []
    fail_streak = 0
    nudges = 0
    finish_rejections = 0
    empty_turns = 0
    any_tool_ran = False
    t0 = time.time()

    for step in range(1, MAX_STEPS + 1):
        resp = chat(model, trim_history(messages), think)
        msg = resp["message"]
        messages.append(msg)

        ec, ed = resp.get("eval_count"), resp.get("eval_duration")
        tps = f", {ec / (ed / 1e9):.0f} tok/s" if ec and ed else ""

        calls = msg.get("tool_calls") or []
        if not calls:
            calls = extract_text_tool_calls(msg.get("content", "") or "")
        if not calls:
            final = (msg.get("content", "") or "").strip()
            if '"arguments"' in final:
                # Looks like a tool call we couldn't parse — don't return it as
                # an answer; tell the model to reissue it properly.
                log.write(kind="malformed_tool_call", step=step, content=final[:400])
                messages.append({
                    "role": "user",
                    "content": "[HARNESS] That tool call was malformed JSON and was NOT "
                               "executed. Re-issue it as a proper tool call.",
                })
                continue
            if final and not any_tool_ran:
                # Plan-first prompting: the opening turn may be a bare plan.
                log.write(kind="plan", step=step, content=final[:400])
                messages.append({
                    "role": "user",
                    "content": "[HARNESS] Good — now execute that plan with tool calls.",
                })
                continue
            if final:
                log.write(kind="end", reason="text_answer", answer=final[:500])
                return final
            # Silent turn (qwen3.5:4b did this mid-task): nudge before giving up.
            empty_turns += 1
            log.write(kind="empty_turn", step=step, count=empty_turns)
            if empty_turns >= 3:
                log.write(kind="end", reason="went_silent")
                return ("Stopped: the model returned 3 empty responses. "
                        "Partial work is in ./workspace — see .runs/ for the transcript.")
            messages.append({
                "role": "user",
                "content": "[HARNESS] Your response was empty. Continue the task with "
                           "a tool call, or call `finish` if everything is verified.",
            })
            continue

        for call in calls:
            fn = call["function"]["name"]
            args = call["function"].get("arguments", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            print(f"  [step {step}] -> {fn}({', '.join(args)}){tps}")

            if fn == "finish":
                problem = independent_verification(task)
                if problem is None:
                    summary = str(args.get("summary", "Done.")).strip()
                    evidence = str(args.get("evidence", "")).strip()
                    log.write(kind="end", reason="finish", summary=summary,
                              steps=step, seconds=round(time.time() - t0, 1))
                    return summary + (f"\n\nEvidence: {evidence}" if evidence else "")
                finish_rejections += 1
                log.write(kind="finish_rejected", problem=problem[:500])
                if finish_rejections >= 3:
                    return ("Stopped: `finish` was rejected 3 times by independent "
                            f"verification. Last problem: {problem}\nPartial work is in ./workspace.")
                print(f"      finish REJECTED: {problem.splitlines()[0][:100]}")
                messages.append({
                    "role": "tool", "name": "finish",
                    "content": f"REJECTED — independent verification failed: {problem}\nFix this, verify, then call finish again.",
                })
                continue

            any_tool_ran = True

            # ---- loop detection ------------------------------------------- #
            sig = fn + "|" + json.dumps(args, sort_keys=True)[:300]
            call_sigs.append(sig)
            repeats = call_sigs.count(sig)
            if repeats >= LOOP_ABORT_AT:
                log.write(kind="end", reason="loop_abort", call=sig[:200])
                return (f"Stopped: the model repeated the same {fn} call {repeats} "
                        "times. Partial work is in ./workspace — see .runs/ for the transcript.")

            try:
                result = TOOLS[fn](**args) if fn in TOOLS else f"ERROR: unknown tool {fn}"
            except Exception as e:  # noqa: BLE001
                result = f"ERROR calling {fn}: {e}"
            result = str(result)[:TOOL_RESULT_CAP]

            failed = result.startswith("ERROR") or "[EXIT" in result[:12] or "Traceback" in result
            fail_streak = fail_streak + 1 if failed else 0

            log.write(kind="tool", step=step, fn=fn,
                      args=json.dumps(args)[:400], result=result[:400], failed=failed)
            if os.environ.get("LOCAL_AGENT_DEBUG"):
                print(f"      args: {json.dumps(args)[:300]}")
                print(f"      result: {result[:300]}")

            if (repeats >= LOOP_NUDGE_AT or fail_streak >= LOOP_NUDGE_AT) and nudges < 3:
                nudges += 1
                result += (
                    "\n\n[HARNESS WARNING] You are going in circles "
                    f"(same call x{repeats}, failure streak {fail_streak}). Stop. "
                    "Re-read the LAST FULL ERROR above, state a NEW hypothesis in one "
                    "sentence, and take a DIFFERENT action (read_file the code, or "
                    "edit_file a targeted fix — do not rewrite the whole file again)."
                )
            messages.append({"role": "tool", "name": fn, "content": result})

    log.write(kind="end", reason="max_steps")
    return "Stopped: hit the max step limit. Partial work is in ./workspace."

# --------------------------------------------------------------------------- #
# Escalation — local-first, frontier-fallback (the pattern behind every good
# agent stack in 2026: cheap model does the work, strong model unblocks it).
# Uses the Claude Code CLI, which runs on the owner's existing Max plan.
# --------------------------------------------------------------------------- #

ESCALATE_TOOLS = ",".join([
    "Read", "Glob", "Grep", "Edit", "Write",
    "Bash(python3:*)", "Bash(python:*)", "Bash(pytest:*)", "Bash(ls:*)",
])


def escalate_to_claude(task: str, failure: str) -> str:
    """Hand a failed task to Claude Code, scoped to the workspace with a tight
    tool allowlist. Its result must still pass independent_verification —
    the harness trusts no model, frontier or not."""
    if not shutil.which("claude"):
        return "Escalation unavailable: `claude` CLI not found."
    files = "\n".join(
        str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    prompt = (
        "A small local model attempted this task in the current directory and failed.\n\n"
        f"TASK: {task}\n\n"
        f"HOW IT FAILED: {failure}\n\n"
        f"Files present:\n{files or '(none)'}\n\n"
        "Fix or finish the task with minimal changes. If the task asks for tests, "
        "make sure a test_*.py file exists and passes. Verify by running the tests "
        "before you stop."
    )
    env = os.environ.copy()
    if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        # Launched from a context that didn't source ~/.zshenv (script, cron):
        # pick up the long-lived token directly so auth never depends on the shell.
        zshenv = Path.home() / ".zshenv"
        if zshenv.exists():
            m = re.search(r"CLAUDE_CODE_OAUTH_TOKEN=(\S+)", zshenv.read_text())
            if m:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = m.group(1).strip("'\"")
    print("  [escalate] local model failed — handing off to Claude Code…")
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", ESCALATE_TOOLS],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=900, env=env,
        )
    except subprocess.TimeoutExpired:
        return "Escalation failed: Claude Code timed out after 15 minutes."
    except OSError as e:
        return f"Escalation failed: {e}"
    tail = (proc.stdout or "").strip()[-1200:] or (proc.stderr or "").strip()[-400:]
    if "Not logged in" in tail:
        return ("Escalation unavailable: the claude CLI has no valid credentials in "
                "non-interactive mode. One-time fix: run `claude setup-token` in a "
                "terminal, then `export CLAUDE_CODE_OAUTH_TOKEN=<token>` (e.g. in ~/.zshenv). "
                f"The local model's failure stands: {failure}")
    problem = independent_verification(task)
    if problem is None and proc.returncode == 0:
        return f"ESCALATED to Claude Code — now passes independent verification.\n\n{tail}"
    return (f"Escalation ran but verification still fails: {problem or f'exit {proc.returncode}'}\n\n{tail}")


def maybe_escalate(answer: str, task: str, enabled: bool) -> str:
    if enabled and answer.startswith("Stopped:"):
        return escalate_to_claude(task, answer)
    return answer

# --------------------------------------------------------------------------- #
# Model selection
# --------------------------------------------------------------------------- #

def pulled_models() -> set[str]:
    try:
        return {m["model"] for m in ollama.list().get("models", [])}
    except Exception as e:  # noqa: BLE001
        sys.exit(
            f"Cannot reach Ollama ({e}).\n"
            "Start it with:  ollama serve   (or open the Ollama app)."
        )


def pick_model(explicit: str | None, escalate: bool = False) -> str:
    local = pulled_models()
    if explicit:
        if explicit in local or explicit.split(":")[0] in {m.split(":")[0] for m in local}:
            return explicit
        sys.exit(f"Model '{explicit}' not pulled. Run:  ollama pull {explicit}")
    if escalate and SPEED_MODEL in local:
        return SPEED_MODEL
    for m in PREFERRED_MODELS:
        if m in local:
            return m
    if local:
        return sorted(local)[0]
    sys.exit("No models pulled. Run:  ollama pull qwen3.5:4b")

# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description="Local self-verifying coding agent v2 (Ollama).")
    ap.add_argument("task", nargs="*", help="Task for the agent. Omit for interactive mode.")
    ap.add_argument("--model", default=os.environ.get("LOCAL_AGENT_MODEL"),
                    help="Ollama model (default: best pulled, preferring qwen3.5:4b)")
    ap.add_argument("--think", action="store_true",
                    help="Enable thinking mode (Qwen3 family) — slower, better on hard tasks")
    ap.add_argument("--escalate", action="store_true",
                    default=bool(os.environ.get("LOCAL_AGENT_ESCALATE")),
                    help="If the local model fails, hand the task to Claude Code "
                         "(workspace-scoped, verified independently; uses your Claude plan)")
    args = ap.parse_args()

    model = pick_model(args.model, args.escalate)
    print(f"Model: {model}  |  ctx: {NUM_CTX}  |  think: {args.think}  |  workspace: {WORKSPACE}")

    if args.task:
        answer = run_agent(" ".join(args.task), model, args.think)
        answer = maybe_escalate(answer, " ".join(args.task), args.escalate)
        print("\n" + "=" * 60 + "\n" + answer)
        return

    print("Interactive mode. Type a task, or 'exit'.")
    while True:
        try:
            task = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if task.lower() in {"exit", "quit"}:
            break
        if task:
            print(maybe_escalate(run_agent(task, model, args.think), task, args.escalate))


if __name__ == "__main__":
    main()
