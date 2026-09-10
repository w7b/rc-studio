"""Run from a source checkout without relying on an old editable installation."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/backend/src'))

from realcenter_marketing.presentation.http.server import main

if __name__ == '__main__':
    main()
