# AI-agent planner language boundary lab

An AI planner that only needs graph operations can still execute unrelated Python statements if its plan is passed to Python execution.

This offline experiment isolates the **exact `ExecutionAction` class** from a pinned MindSearch revision and supplies an inert graph recorder. It compares that action with a proposed interpreter that accepts only literal graph-operation statements. All inputs are fixed synthetic fixtures. No model, MindSearch server, search agent, external request, credential, shell command or real file operation is involved.

## Result

Across 19 chosen inputs and two methods (38 rows), the source action appended a harmless `NOTE` to an in-memory sentinel list in all five extra-statement fixtures. The proposed interpreter appended none and rejected those inputs before changing the graph. Seven supported ordinary plans, including Unicode and a quoted marker, produced identical states and results under both methods.

These are deterministic fixture counts, not attack-success probabilities. Twelve focused tests passed. Two functional mutations were detected: restoring Python execution and validating statements incrementally while applying the valid prefix.

| Chosen family | Inputs | Source sentinel changed | Literal-plan sentinel changed | Main observation |
|---|---:|---:|---:|---|
| Supported ordinary plans | 7 | 0 | 0 | Exact outputs and state agree |
| Extra in-memory statement | 5 | 5 | 0 | Proposed interpreter rejects before any graph change |
| Other restricted Python | 4 | 0 | 0 | Harmless Python features are intentionally excluded |
| Selector text inside literal | 1 | 0 | 0 | Source regex misreads string contents as a node selection |
| Later missing-node error | 1 | 0 | 0 | Both retain the earlier graph change |
| Malformed syntax | 1 | 0 | 0 | Neither starts graph work |

[Exact paired records](artifacts/run.json) · [Human evidence](evidence.md) · [Tests](artifacts/tests.json) · [Mutation results](artifacts/mutations.json).

## Hypothesis and threat model

Assume an adversary can already supply the command string to the planner action. The experiment does not demonstrate how an attacker obtains that access, whether an application is reachable, or whether a model generates the string. The loader, pinned source, fixture graph, operation map and recorder remain trusted.

Hypothesis: the source action admits harmless non-graph Python effects, whereas whole-plan parsing into a small literal-operation language excludes those effects while preserving supported graph plans. The intervention is an independent proposed design, **not a released MindSearch fix or a complete sandbox**.

Control is the unmodified source class with an inert `Graph`. Intervention parses the entire plan, decodes only literal string arguments, then uses an explicit trusted handler map. It does not evaluate the input as Python. Sentinel contents, graph events, nodes, selected results and exceptions are recorded independently of whether the method returns successfully.

## Setup and exact commands

Tested with Python 3.11.6. Standard library only; no dependency installation or network needed.

```sh
python3 experiment.py
python3 -m unittest -v test_experiment
python3 run_checks.py
```

The first command writes `artifacts/run.json` and `evidence.md`. The last writes test and mutation artifacts and exits nonzero unless the 12 tests pass and both mutations are detected. Mutation copies live in temporary directories and are deleted afterward. Test durations and temporary paths are normalized in saved artifacts to permit byte-for-byte reproduction.

Do not modify the control to execute arbitrary input. Its API rejects strings outside the checked-in fixed fixture set. Empty builtins, fixed inputs and inert graph are harness constraints, not upstream defenses and not a security boundary suitable for untrusted Python.

## Technical walkthrough

The source action extracts code from fenced or inline text, calls Python `exec`, and only then uses a regular expression to locate `graph.node(...)` selections. Its method is a generator because of a streaming branch. Simply calling it would not execute the command; this harness advances it and captures the returned value. The inert graph always has zero active search tasks, so the source streaming branch and real search are not exercised.

The witness `extra_before` first appends `NOTE` to a supplied in-memory list, then creates the same root, node and edge as the ordinary plan. Source executes the append and returns the rain node. The literal-plan interpreter rejects the first extra operation, leaving both the graph and sentinel empty. It refuses the whole plan; it does not execute a cleaned version.

`quoted_marker` places the same `sentinel.append('NOTE')` characters inside a literal node-content string. Both methods store the literal text and leave the sentinel empty. The boundary is the accepted language structure, not a blacklist of marker words.

`prefix_then_extra` starts with an allowed root creation, then contains the extra append. Eager compilation rejects the entire plan before that root is created. The incremental-validation mutation creates the root first, and the tests detect it.

`extra_before_runtime_error` appends the marker before trying to read a missing node. Source raises `KeyError` after the append. Checking only the error would miss the effect. Separately, `prefix_then_missing_node` is syntactically accepted by both methods: both create the root and then raise `KeyError`. Whole-plan syntax checking is not a transaction and does not roll back runtime errors.

### Proposed language

Allowed statements are calls on the exact name `graph`: `add_root_node`, `add_node`, `add_edge`, or `node`. Arguments must be string literals in the specified positions or named parameters; duplicate, missing or unknown parameters are rejected. Only `node_name='root'` for root creation has a default. Nested expressions, assignments, unknown methods and non-string values are excluded. Input is limited to 8192 UTF-8 bytes, 64 statements and 1024 bytes per literal. These are illustrative resource bounds, not a denial-of-service proof.

Whole Python/inline fences are supported. Unlike the source's first-match extraction, the proposed parser rejects surrounding prose. It also uses parsed `node` operations for selection instead of scanning string contents with a regular expression. `selector_in_literal` documents this secondary compatibility difference: source stores a string containing node-selection syntax, then its regex produces a missing-node error; the interpreter leaves that text as content.

The recorder's methods do not launch real searches. `add_node` only changes a dictionary; `add_edge` records stable names rather than upstream UUID/state objects. Therefore matching fixture outputs establishes agreement inside this recorder, not full graph-runtime compatibility.

## Source and attribution

- [Unreviewed GitHub advisory GHSA-4535-w5r2-pmqp](https://github.com/advisories/GHSA-4535-w5r2-pmqp), checked October 4, 2026. The current page shows CVSS v4 9.3 and unknown patched-version metadata. Its description names MindSearch 0.1.0 and an `inputs` argument. This lab does not reproduce that deployment or claim version equivalence.
- [Pinned source](https://github.com/InternLM/MindSearch/blob/7952c5f8a956fe6a44228a6a7d528a35340e7c87/mindsearch/agent/graph.py), commit `7952c5f8a956fe6a44228a6a7d528a35340e7c87`, Git blob `b9a09f1040418ae5b0b71fa66d3d80ce8e65eb3c`. It uses a `command` parameter. `ExecutionAction` spans lines 248–307, its method begins at 251. Full public file is retained as inert text in `vendor/graph.py.txt`; only the exact class AST is compiled.
- [Pin and hashes](vendor/source.json), [upstream Apache 2.0 license](vendor/LICENSE), and [attribution](NOTICE). No private source document is part of this repository.

## Limitations and engineering check

No live-model decision, prompt-injection success rate, remote exploit, application authentication, complete MindSearch integration or production sandbox is tested. A model could still choose harmful allowed operations. The small language trades expressiveness for a narrower host interface; it rejects even harmless computed strings. Parser acceptance does not establish authorization, graph validity, budget compliance, side-effect rollback or downstream search safety.

For a planner that only needs these operations, parse and validate the entire bounded plan into literal operation records before invoking trusted handlers. Test extra statements at both ends, quoted lookalikes, normal plans and failure-after-effect cases; separately add the permissions, state validation or transaction behavior that the real handlers require.
