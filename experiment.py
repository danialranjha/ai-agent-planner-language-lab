"""Fixed-fixture MindSearch component assay. Never pass untrusted code to control."""
import ast
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_SHA256 = 'ef42f61fbfef47e60dbecfd30865ad1bf0557889c78eaca75579763c242319ac'


class Graph:
    """Inert recorder, NOT upstream WebSearchGraph or a search implementation."""
    def __init__(self):
        self.nodes = {}
        self.adjacency_list = {}
        self.events = []
        self.n_active_tasks = 0

    def add_root_node(self, node_content, node_name='root'):
        self.events.append(['add_root_node', node_content, node_name])
        self.nodes[node_name] = {'content': node_content, 'type': 'root'}
        self.adjacency_list[node_name] = []

    def add_node(self, node_name, node_content):
        self.events.append(['add_node', node_name, node_content])
        self.nodes[node_name] = {'content': node_content, 'type': 'searcher'}
        self.adjacency_list[node_name] = []

    def add_edge(self, start_node, end_node):
        self.events.append(['add_edge', start_node, end_node])
        if start_node not in self.nodes or end_node not in self.nodes:
            raise KeyError('missing edge node')
        self.adjacency_list[start_node].append(end_node)

    def node(self, node_name):
        self.events.append(['node', node_name])
        return self.nodes[node_name].copy()


def load_source_action():
    raw = (ROOT / 'vendor/graph.py.txt').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('upstream source mismatch')
    tree = ast.parse(raw.decode())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ExecutionAction')
    # Only the exact class is compiled; unrelated imports/classes never execute.
    module = ast.Module(body=[cls], type_ignores=[])
    namespace = {'BaseAction': object, 're': re}
    exec(compile(module, 'pinned-MindSearch-ExecutionAction', 'exec'), namespace)
    return namespace['ExecutionAction']()


SCHEMA = {
    'add_root_node': (('node_content', 'node_name'), {'node_name': 'root'}),
    'add_node': (('node_name', 'node_content'), {}),
    'add_edge': (('start_node', 'end_node'), {}),
    'node': (('node_name',), {}),
}


class Rejected(ValueError):
    pass


def normalize_plan(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 8192:
        raise Rejected('plan size/type')
    text = text.strip()
    # Unlike upstream's first-match extraction, only a whole fenced plan is accepted.
    if text.startswith('```'):
        match = re.fullmatch(r'```(?:python)?\n(.*?)\n```', text, re.DOTALL)
        if not match:
            raise Rejected('whole python fence required')
        text = match.group(1)
    elif text.startswith('`'):
        match = re.fullmatch(r'`([^`]*)`', text, re.DOTALL)
        if not match:
            raise Rejected('whole inline fence required')
        text = match.group(1)
    return text


def parse_statements(text):
    try:
        body = ast.parse(normalize_plan(text), mode='exec').body
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise Rejected('parse error') from exc
    if len(body) > 64:
        raise Rejected('too many statements')
    return body


def decode_statement(stmt):
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        raise Rejected('only graph operation statements')
    call = stmt.value
    fn = call.func
    if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
            and fn.value.id == 'graph' and fn.attr in SCHEMA):
        raise Rejected('unknown operation')
    names, defaults = SCHEMA[fn.attr]
    if len(call.args) > len(names):
        raise Rejected('too many arguments')
    values = {}
    for key, arg in list(zip(names, call.args)) + [(k.arg, k.value) for k in call.keywords]:
        if key not in names or key in values:
            raise Rejected('unknown or duplicate argument')
        if not isinstance(arg, ast.Constant) or type(arg.value) is not str:
            raise Rejected('literal strings only')
        if len(arg.value.encode('utf-8')) > 1024:
            raise Rejected('literal too large')
        values[key] = arg.value
    for key in names:
        if key not in values:
            if key not in defaults:
                raise Rejected('missing argument')
            values[key] = defaults[key]
    return fn.attr, [values[key] for key in names]


def compile_plan(text):
    # Eager validation is intentional: no valid prefix executes before a later rejection.
    return [decode_statement(stmt) for stmt in parse_statements(text)]


def run_intervention(text, graph, sentinel):
    operations = compile_plan(text)
    selected = []
    handlers = {'add_root_node': graph.add_root_node, 'add_node': graph.add_node,
                'add_edge': graph.add_edge, 'node': graph.node}
    for name, args in operations:
        result = handlers[name](*args)
        if name == 'node':
            selected.append(result)
    return selected, graph.nodes, graph.adjacency_list


ORDINARY = "graph.add_root_node('weather'); graph.add_node('a', 'rain'); graph.add_edge('root', 'a'); graph.node('a')"
PREFIX = "graph.add_root_node('weather')"
FIXTURES = [
    ('ordinary', 'supported', ORDINARY),
    ('fenced_ordinary', 'supported', '```python\n' + ORDINARY + '\n```'),
    ('inline_ordinary', 'supported', '`' + ORDINARY + '`'),
    ('keywords', 'supported', "graph.add_root_node(node_content='weather', node_name='r'); graph.node('r')"),
    ('unicode_literal', 'supported', "graph.add_root_node('café 雨 😀'); graph.node('root')"),
    ('quoted_marker', 'supported', "graph.add_root_node(\"sentinel.append('NOTE')\"); graph.node('root')"),
    ('empty', 'supported', ''),
    ('extra_before', 'extra_statement', "sentinel.append('NOTE'); " + ORDINARY),
    ('extra_after', 'extra_statement', ORDINARY + "; sentinel.append('NOTE')"),
    ('fenced_extra', 'extra_statement', "```python\nsentinel.append('NOTE'); " + ORDINARY + '\n```'),
    ('extra_before_runtime_error', 'extra_statement', "sentinel.append('NOTE'); graph.node('missing')"),
    ('prefix_then_extra', 'extra_statement', PREFIX + "; sentinel.append('NOTE')"),
    ('prefix_then_assignment', 'restricted_python', PREFIX + '; scratch = 1'),
    ('computed_literal', 'restricted_python', "graph.add_root_node('wea' + 'ther')"),
    ('nested_expression', 'restricted_python', "graph.add_root_node('weather'.upper())"),
    ('unknown_graph_method', 'restricted_python', 'graph.nodes.clear()'),
    ('selector_in_literal', 'selector_limit', 'graph.add_root_node("graph.node(\'missing\')")'),
    ('prefix_then_missing_node', 'runtime_limit', PREFIX + "; graph.node('missing')"),
    ('syntax_error', 'malformed', 'graph.add_root_node('),
]
FIXED_INPUTS = frozenset(text for _, _, text in FIXTURES)


def run_control(text, graph, sentinel):
    if text not in FIXED_INPUTS:
        raise ValueError('control only runs reviewed fixed fixtures')
    action = load_source_action()
    local = {'graph': graph, 'sentinel': sentinel}
    # Harness containment: this is not an upstream sandbox and not safe for arbitrary code.
    pending = action.run(text, local, {'__builtins__': {}})
    try:
        next(pending)
    except StopIteration as done:
        return done.value
    raise AssertionError('inert graph unexpectedly streamed')


def observe(text, method):
    graph, sentinel = Graph(), []
    result, error = None, None
    try:
        runner = run_control if method == 'source' else run_intervention
        result = runner(text, graph, sentinel)
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    return copy.deepcopy({'method': method, 'sentinel': sentinel, 'events': graph.events,
                          'nodes': graph.nodes, 'edges': graph.adjacency_list,
                          'result': result, 'error': error})


def run():
    cases = [{'id': name, 'family': family, 'command': command,
              'observations': [observe(command, m) for m in ['source', 'literal_plan']]}
             for name, family, command in FIXTURES]
    counts = {}
    for method in ['source', 'literal_plan']:
        rows = [next(o for o in c['observations'] if o['method'] == method) for c in cases]
        counts[method] = {'rows': len(rows), 'sentinel_changed': sum(bool(o['sentinel']) for o in rows),
                          'errors': sum(o['error'] is not None for o in rows)}
    return {'schema': 1, 'scope': 'exact source component, synthetic graph, fixed fixtures, no model/network',
            'upstream_commit': '7952c5f8a956fe6a44228a6a7d528a35340e7c87',
            'source_sha256': SOURCE_SHA256, 'counts': counts, 'cases': cases}


def evidence(data):
    lines = ['# Exact component evidence', '', 'Fixed deterministic fixtures, not attack rates. A source exception does not undo earlier effects.', '',
             '| Fixture | Source sentinel | Literal-plan sentinel | Source error | Literal-plan error |',
             '|---|---|---|---|---|']
    for c in data['cases']:
        a, b = c['observations']
        lines.append(f"| {c['id']} | {a['sentinel']} | {b['sentinel']} | {a['error']['type'] if a['error'] else 'none'} | {b['error']['type'] if b['error'] else 'none'} |")
    lines.extend(['', '## Paired witness', '',
      "`extra_before`: the fixed command appends `NOTE` to an in-memory list, then runs the ordinary graph plan. Source records the append and returns the selected rain node. Literal-plan rejects the extra operation before changing either list or graph.", '',
      '`quoted_marker` stores those same characters as ordinary graph content under both methods; neither appends anything.', '',
      '## Limits made visible', '',
      '`extra_before_runtime_error`: source appends NOTE, then raises KeyError. An error result is not proof that nothing happened.', '',
      '`prefix_then_extra`: eager full-plan validation prevents the ordinary prefix from changing the graph before rejecting the later extra operation.', '',
      '`prefix_then_missing_node`: both methods add the root, then raise KeyError. Syntax validation does not provide transaction rollback or prevalidate graph state.', '',
      '`computed_literal` and `nested_expression`: the proposed language rejects harmless Python expressions. It is deliberately less expressive, not a compatible sandbox.', '',
      '`selector_in_literal`: upstream regex sees graph.node text inside a string and fails after storing it; the interpreter treats the string literally and has no selected-node request. This is a secondary result-selection limitation, not a new remote exploit.', ''])
    return '\n'.join(lines)


if __name__ == '__main__':
    data = run()
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'artifacts/run.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    (ROOT / 'evidence.md').write_text(evidence(data))
    print(json.dumps(data['counts'], indent=2))
