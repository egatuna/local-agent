# Graph Report - local-agent  (2026-07-07)

## Corpus Check
- 3 files · ~4,111 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 56 nodes · 64 edges · 17 communities (5 shown, 12 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4f527ceb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- [[_COMMUNITY_Independent finish verification|Independent finish verification]]
- [[_COMMUNITY_Loop detection with escalating nudges|Loop detection with escalating nudges]]
- [[_COMMUNITY_Model tiers (SpeedQualityMid)|Model tiers (Speed/Quality/Mid)]]
- [[_COMMUNITY_ReAct tool loop (local model)|ReAct tool loop (local model)]]
- [[_COMMUNITY_Run transcripts (.runs.jsonl)|Run transcripts (.runs/*.jsonl)]]
- [[_COMMUNITY_Trust No Model principle|Trust No Model principle]]
- [[_COMMUNITY_Workspace-scoped sandboxing|Workspace-scoped sandboxing]]

## God Nodes (most connected - your core abstractions)
1. `_safe_path()` - 8 edges
2. `run_agent()` - 8 edges
3. `independent_verification()` - 6 edges
4. `local-agent` - 6 edges
5. `search()` - 5 edges
6. `escalate_to_claude()` - 5 edges
7. `RunLog` - 4 edges
8. `main()` - 4 edges
9. `run_python()` - 3 edges
10. `run_shell()` - 3 edges

## Surprising Connections (you probably didn't know these)
- `Ollama on-device runtime` --references--> `ollama Python package (>=0.4.0)`  [EXTRACTED]
  README.md → requirements.txt

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Self-verifying run loop: verification, loop detection, escalation** — readme_independent_finish_verification, readme_loop_detection, readme_escalation [EXTRACTED 0.90]

## Communities (17 total, 12 thin omitted)

### Community 0 - "Agent Loop & Chat"
Cohesion: 0.22
Nodes (8): chat(), extract_text_tool_calls(), Fallback for small models that print tool calls as JSON text instead of     usin, Keep the KV cache off swap: elide old tool results once history is long.     Sys, One model call with thinking-mode support and transient-error retries., run_agent(), RunLog, trim_history()

### Community 1 - "CLI & Model Selection"
Cohesion: 0.24
Nodes (11): edit_file(), list_dir(), main(), maybe_escalate(), pick_model(), pulled_models(), Resolve a path and refuse anything that escapes the workspace.      Forgiving: s, read_file() (+3 more)

### Community 2 - "Verification & Escalation"
Cohesion: 0.33
Nodes (7): escalate_to_claude(), _has_pytest(), independent_verification(), Literal-text grep across workspace files., Return None if the workspace passes verification, else a rejection reason., Hand a failed task to Claude Code, scoped to the workspace with a tight     tool, search()

### Community 4 - "Code Execution Tools"
Cohesion: 0.40
Nodes (5): Run a Python snippet inside the workspace and return stdout+stderr.      Conveni, Run a shell command inside the workspace (sandboxed to that dir)., _run(), run_python(), run_shell()

### Community 5 - "Trust-No-Model Principle"
Cohesion: 0.29
Nodes (6): Architecture, Configuration, Harness features, local-agent, Model tiers (benchmarked 2026-07-06, 8 GB M3), Quick start

## Knowledge Gaps
- **12 isolated node(s):** `bootstrap.sh script`, `Architecture`, `Quick start`, `Model tiers (benchmarked 2026-07-06, 8 GB M3)`, `Harness features` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_safe_path()` connect `CLI & Model Selection` to `Verification & Escalation`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `run_agent()` connect `Agent Loop & Chat` to `CLI & Model Selection`, `Verification & Escalation`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `RunLog` connect `Agent Loop & Chat` to `CLI & Model Selection`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **What connects `bootstrap.sh script`, `Resolve a path and refuse anything that escapes the workspace.      Forgiving: s`, `Literal-text grep across workspace files.` to the rest of the system?**
  _27 weakly-connected nodes found - possible documentation gaps or missing edges._