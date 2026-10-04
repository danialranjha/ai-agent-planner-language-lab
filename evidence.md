# Exact component evidence

Fixed deterministic fixtures, not attack rates. A source exception does not undo earlier effects.

| Fixture | Source sentinel | Literal-plan sentinel | Source error | Literal-plan error |
|---|---|---|---|---|
| ordinary | [] | [] | none | none |
| fenced_ordinary | [] | [] | none | none |
| inline_ordinary | [] | [] | none | none |
| keywords | [] | [] | none | none |
| unicode_literal | [] | [] | none | none |
| quoted_marker | [] | [] | none | none |
| empty | [] | [] | none | none |
| extra_before | ['NOTE'] | [] | none | Rejected |
| extra_after | ['NOTE'] | [] | none | Rejected |
| fenced_extra | ['NOTE'] | [] | none | Rejected |
| extra_before_runtime_error | ['NOTE'] | [] | KeyError | Rejected |
| prefix_then_extra | ['NOTE'] | [] | none | Rejected |
| prefix_then_assignment | [] | [] | none | Rejected |
| computed_literal | [] | [] | none | Rejected |
| nested_expression | [] | [] | none | Rejected |
| unknown_graph_method | [] | [] | none | Rejected |
| selector_in_literal | [] | [] | KeyError | none |
| prefix_then_missing_node | [] | [] | KeyError | KeyError |
| syntax_error | [] | [] | SyntaxError | Rejected |

## Paired witness

`extra_before`: the fixed command appends `NOTE` to an in-memory list, then runs the ordinary graph plan. Source records the append and returns the selected rain node. Literal-plan rejects the extra operation before changing either list or graph.

`quoted_marker` stores those same characters as ordinary graph content under both methods; neither appends anything.

## Limits made visible

`extra_before_runtime_error`: source appends NOTE, then raises KeyError. An error result is not proof that nothing happened.

`prefix_then_extra`: eager full-plan validation prevents the ordinary prefix from changing the graph before rejecting the later extra operation.

`prefix_then_missing_node`: both methods add the root, then raise KeyError. Syntax validation does not provide transaction rollback or prevalidate graph state.

`computed_literal` and `nested_expression`: the proposed language rejects harmless Python expressions. It is deliberately less expressive, not a compatible sandbox.

`selector_in_literal`: upstream regex sees graph.node text inside a string and fails after storing it; the interpreter treats the string literally and has no selected-node request. This is a secondary result-selection limitation, not a new remote exploit.
