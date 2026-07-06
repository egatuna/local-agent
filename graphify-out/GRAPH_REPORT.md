# Graph Report - /Users/eanngatuna/local-agent  (2026-07-06)

## Corpus Check
- Corpus is ~4,076 words - fits in a single context window. You may not need a graph.

## Summary
- 50 nodes · 72 edges · 10 communities (9 shown, 1 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.57)
- Token cost: 37,220 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Agent Loop & Chat|Agent Loop & Chat]]
- [[_COMMUNITY_CLI & Model Selection|CLI & Model Selection]]
- [[_COMMUNITY_Verification & Escalation|Verification & Escalation]]
- [[_COMMUNITY_Workspace Sandbox & File IO|Workspace Sandbox & File IO]]
- [[_COMMUNITY_Code Execution Tools|Code Execution Tools]]
- [[_COMMUNITY_Trust-No-Model Principle|Trust-No-Model Principle]]
- [[_COMMUNITY_Ollama Runtime & Context|Ollama Runtime & Context]]
- [[_COMMUNITY_Tool-Loop Concepts|Tool-Loop Concepts]]
- [[_COMMUNITY_Escalation & Model Tiers|Escalation & Model Tiers]]
- [[_COMMUNITY_Bootstrap Setup|Bootstrap Setup]]

## God Nodes (most connected - your core abstractions)
1. `_safe_path()` - 8 edges
2. `run_agent()` - 8 edges
3. `independent_verification()` - 6 edges
4. `search()` - 5 edges
5. `escalate_to_claude()` - 5 edges
6. `RunLog` - 4 edges
7. `main()` - 4 edges
8. `Escalation to Claude Code CLI` - 4 edges
9. `ReAct tool loop (local model)` - 4 edges
10. `Ollama on-device runtime` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Ollama on-device runtime` --references--> `ollama Python package (>=0.4.0)`  [EXTRACTED]
  README.md → requirements.txt

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Self-verifying run loop: verification, loop detection, escalation** — readme_independent_finish_verification, readme_loop_detection, readme_escalation [EXTRACTED 0.90]

## Communities (10 total, 1 thin omitted)

### Community 0 - "Agent Loop & Chat"
Cohesion: 0.22
Nodes (8): chat(), extract_text_tool_calls(), Fallback for small models that print tool calls as JSON text instead of     usin, Keep the KV cache off swap: elide old tool results once history is long.     Sys, One model call with thinking-mode support and transient-error retries., run_agent(), RunLog, trim_history()

### Community 1 - "CLI & Model Selection"
Cohesion: 0.36
Nodes (6): edit_file(), main(), maybe_escalate(), pick_model(), pulled_models(), write_file()

### Community 2 - "Verification & Escalation"
Cohesion: 0.33
Nodes (7): escalate_to_claude(), _has_pytest(), independent_verification(), Literal-text grep across workspace files., Return None if the workspace passes verification, else a rejection reason., Hand a failed task to Claude Code, scoped to the workspace with a tight     tool, search()

### Community 3 - "Workspace Sandbox & File IO"
Cohesion: 0.40
Nodes (5): list_dir(), Resolve a path and refuse anything that escapes the workspace.      Forgiving: s, read_file(), _safe_path(), Path

### Community 4 - "Code Execution Tools"
Cohesion: 0.40
Nodes (5): Run a Python snippet inside the workspace and return stdout+stderr.      Conveni, Run a shell command inside the workspace (sandboxed to that dir)., _run(), run_python(), run_shell()

### Community 5 - "Trust-No-Model Principle"
Cohesion: 0.50
Nodes (4): Independent finish verification, local-agent (self-verifying on-device coding agent), Run transcripts (.runs/*.jsonl), Trust No Model principle

### Community 6 - "Ollama Runtime & Context"
Cohesion: 0.67
Nodes (3): Context trimming (KV cache off swap), Ollama on-device runtime, ollama Python package (>=0.4.0)

### Community 7 - "Tool-Loop Concepts"
Cohesion: 1.00
Nodes (3): edit_file exact-snippet replacement tool, Loop detection with escalating nudges, ReAct tool loop (local model)

### Community 8 - "Escalation & Model Tiers"
Cohesion: 0.67
Nodes (3): Escalation to Claude Code CLI, Model tiers (Speed/Quality/Mid), Workspace-scoped sandboxing

## Knowledge Gaps
- **3 isolated node(s):** `bootstrap.sh script`, `Run transcripts (.runs/*.jsonl)`, `ollama Python package (>=0.4.0)`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_safe_path()` connect `Workspace Sandbox & File IO` to `CLI & Model Selection`, `Verification & Escalation`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `run_agent()` connect `Agent Loop & Chat` to `CLI & Model Selection`, `Verification & Escalation`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `RunLog` connect `Agent Loop & Chat` to `CLI & Model Selection`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **What connects `bootstrap.sh script`, `Resolve a path and refuse anything that escapes the workspace.      Forgiving: s`, `Literal-text grep across workspace files.` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._