import ast
import importlib.util
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / 'src/studio_ai'


def imports(path):
    module = 'studio_ai.' + path.relative_to(PACKAGE).with_suffix('').as_posix().replace('/', '.')
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                yield importlib.util.resolve_name('.' * node.level + (node.module or ''), module.rpartition('.')[0])
            else:
                yield node.module or ''


def test_inner_layers_do_not_depend_on_adapters_or_sdk():
    violations = []
    for layer in ('domain', 'application'):
        for path in (PACKAGE / layer).rglob('*.py'):
            for name in imports(path):
                forbidden = ('agents', 'openai', 'http', 'requests', 'dotenv', 'PIL',
                             'studio_ai.infrastructure', 'studio_ai.bootstrap',
                             'studio_ai.presentation')
                if layer == 'domain':
                    forbidden += ('studio_ai.application',)
                if any(name == item or name.startswith(item + '.') for item in forbidden):
                    violations.append((str(path.relative_to(PACKAGE)), name))
    assert not violations


def test_application_does_not_access_files_or_spawn_threads():
    forbidden = {'read_text', 'write_text', 'read_bytes', 'write_bytes', 'mkdir', 'unlink',
                 'rename', 'rglob', 'glob', 'open', 'Thread', 'Lock'}
    violations = []
    for path in (PACKAGE / 'application').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
                if name in forbidden:
                    violations.append((path.name, node.lineno, name))
    assert not violations


def test_http_has_no_concrete_infrastructure_imports():
    assert not [name for p in (PACKAGE / 'presentation/http').rglob('*.py')
                for name in imports(p) if name.startswith('studio_ai.infrastructure')]
