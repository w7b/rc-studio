import importlib.util
from pathlib import Path


def load_script(name):
    path = Path(__file__).resolve().parents[3] / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(f'studio_script_{name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
