"""Ensures the project root is importable as `src.*` regardless of the CWD pytest is invoked from."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
