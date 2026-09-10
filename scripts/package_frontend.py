"""Verify a frontend build is available before packaging or serving the app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
build = ROOT / 'apps/frontend/dist'
if not (build / 'index.html').is_file() or not any((build / 'assets').glob('*.js')):
    raise SystemExit('Execute npm ci e npm run build em apps/frontend antes de iniciar o site.')
print(f'Frontend pronto: {build}')
