"""Run focused tests and two functional mutations in temporary copies."""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def normalize_log(text):
    text = re.sub(r'Ran (\d+) tests in [0-9.]+s', r'Ran \1 tests in <elapsed>', text)
    return re.sub(r'(?m)^[ \t]*[~^]+[ \t]*\n', '', text)


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_experiment.py')
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    print(log.getvalue())
    tests = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
             'success': result.wasSuccessful(), 'log': normalize_log(log.getvalue())}
    original = (ROOT/'experiment.py').read_text()
    mutations = [
        ('restore_python_execution', '    operations = compile_plan(text)', '    return run_control(text, graph, sentinel)'),
        ('validate_incrementally', '    return [decode_statement(stmt) for stmt in parse_statements(text)]',
         '    return (decode_statement(stmt) for stmt in parse_statements(text))'),
    ]
    reports = []
    for name, before, after in mutations:
        assert original.count(before) == 1
        with tempfile.TemporaryDirectory(prefix='planner-mutation-') as directory:
            target = Path(directory)
            shutil.copytree(ROOT/'vendor', target/'vendor')
            shutil.copy2(ROOT/'test_experiment.py', target/'test_experiment.py')
            (target/'experiment.py').write_text(original.replace(before, after))
            run = subprocess.run([sys.executable,'-m','unittest','-v','test_experiment'], cwd=target,
                                 capture_output=True,text=True,timeout=30)
            output = run.stdout + run.stderr
            failed = re.search(r'FAILED \(failures=(\d+)', output)
            detected = run.returncode == 1 and 'Ran 12 tests in ' in output and failed is not None and int(failed.group(1)) > 0
            reports.append({'name':name,'detected':detected,'returncode':run.returncode,
                            'assertion_failures':int(failed.group(1)) if failed else 0,
                            'output':normalize_log(output.replace(str(target.resolve()), '<temporary-copy>').replace(str(target), '<temporary-copy>'))})
    (ROOT/'artifacts').mkdir(exist_ok=True)
    (ROOT/'artifacts/tests.json').write_text(json.dumps(tests,indent=2)+'\n')
    (ROOT/'artifacts/mutations.json').write_text(json.dumps(reports,indent=2)+'\n')
    print(json.dumps([{'name':r['name'],'detected':r['detected']} for r in reports]))
    return 0 if result.wasSuccessful() and result.testsRun == 12 and all(r['detected'] for r in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
