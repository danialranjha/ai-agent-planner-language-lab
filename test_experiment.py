import ast
import hashlib
import json
import unittest
from unittest.mock import patch
import experiment as e


class BoundaryTests(unittest.TestCase):
    def case(self, name):
        return next(text for key, _, text in e.FIXTURES if key == name)

    def test_source_hash_and_extracted_method(self):
        raw = (e.ROOT / 'vendor/graph.py.txt').read_bytes()
        meta = json.loads((e.ROOT / 'vendor/source.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), e.SOURCE_SHA256)
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(), meta['graph.py.txt']['git_blob'])
        self.assertEqual(e.load_source_action().run.__code__.co_firstlineno, 251)

    def test_extra_statements_change_only_source_sentinel(self):
        for name, family, text in e.FIXTURES:
            if family == 'extra_statement':
                with self.subTest(name=name):
                    a, b = e.observe(text, 'source'), e.observe(text, 'literal_plan')
                    self.assertEqual(a['sentinel'], ['NOTE'])
                    self.assertEqual(b['sentinel'], [])
                    self.assertEqual(b['events'], [])
                    self.assertEqual(b['error']['type'], 'Rejected')

    def test_seven_supported_twins_match_exact_states(self):
        twins = [(name, text) for name, family, text in e.FIXTURES if family == 'supported']
        self.assertEqual(len(twins), 7)
        for name, text in twins:
            with self.subTest(name=name):
                a, b = e.observe(text, 'source'), e.observe(text, 'literal_plan')
                a.pop('method'); b.pop('method')
                self.assertIsNone(a['error'])
                self.assertEqual(a, b)

    def test_no_partial_effect_before_syntax_rejection(self):
        for name in ['prefix_then_extra', 'prefix_then_assignment']:
            got = e.observe(self.case(name), 'literal_plan')
            self.assertEqual(got['nodes'], {})
            self.assertEqual(got['events'], [])
            self.assertEqual(got['sentinel'], [])

    def test_runtime_errors_do_not_undo_effects(self):
        for method in ['source', 'literal_plan']:
            got = e.observe(self.case('prefix_then_missing_node'), method)
            self.assertEqual(got['error']['type'], 'KeyError')
            self.assertEqual(got['nodes']['root']['content'], 'weather')
        got = e.observe(self.case('extra_before_runtime_error'), 'source')
        self.assertEqual(got['error']['type'], 'KeyError')
        self.assertEqual(got['sentinel'], ['NOTE'])

    def test_literal_marker_is_data(self):
        for method in ['source', 'literal_plan']:
            got = e.observe(self.case('quoted_marker'), method)
            self.assertEqual(got['nodes']['root']['content'], "sentinel.append('NOTE')")
            self.assertEqual(got['sentinel'], [])

    def test_unsupported_python_is_rejected(self):
        for name, family, text in e.FIXTURES:
            if family == 'restricted_python':
                with self.subTest(name=name):
                    got = e.observe(text, 'literal_plan')
                    self.assertEqual(got['error']['type'], 'Rejected')
                    self.assertEqual(got['events'], [])

    def test_selector_text_inside_string(self):
        text = self.case('selector_in_literal')
        a, b = e.observe(text, 'source'), e.observe(text, 'literal_plan')
        self.assertEqual(a['nodes'], b['nodes'])
        self.assertEqual(a['error']['type'], 'KeyError')
        self.assertIsNone(b['error'])
        self.assertEqual(b['result'][0], [])

    def test_interpreter_rejects_invalid_argument_forms_and_bounds(self):
        inputs = ['graph.node(1)', "graph.node('x', node_name='y')", 'graph.node()',
                  "graph.node(other='x')", "graph.node(*['x'])", "graph.node(**{'node_name':'x'})",
                  "graph.add_root_node('" + 'x' * 1025 + "')", 'graph.node(\'x\');' * 65,
                  'x' * 8193, "before\n```python\ngraph.node('x')\n```", 'graph.node(']
        for text in inputs:
            with self.subTest(text=text[:60]):
                with self.assertRaises(e.Rejected):
                    e.compile_plan(text)

    def test_source_generator_executes_only_when_advanced(self):
        graph, sentinel = e.Graph(), []
        pending = e.load_source_action().run(self.case('extra_before'), {'graph':graph,'sentinel':sentinel}, {'__builtins__':{}})
        self.assertEqual(sentinel, [])
        with self.assertRaises(StopIteration):
            next(pending)
        self.assertEqual(sentinel, ['NOTE'])

    def test_control_refuses_arbitrary_input_and_no_network_used(self):
        with self.assertRaises(ValueError):
            e.run_control('scratch=2', e.Graph(), [])
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch('socket.getaddrinfo', side_effect=AssertionError('DNS forbidden')):
            data = e.run()
        self.assertEqual(data['counts']['source']['sentinel_changed'], 5)
        self.assertEqual(data['counts']['literal_plan']['sentinel_changed'], 0)

    def test_repeatability_and_literal_roundtrip(self):
        self.assertEqual(e.run(), e.run())
        for value in ['', '雨', "quotes'\"", 'line\nbreak', 'a); scratch = 1', 'graph.node(\'x\')']:
            text = 'graph.add_root_node(' + repr(value) + ')'
            got = e.observe(text, 'literal_plan')
            self.assertIsNone(got['error'])
            self.assertEqual(got['nodes']['root']['content'], value)


if __name__ == '__main__':
    unittest.main()
