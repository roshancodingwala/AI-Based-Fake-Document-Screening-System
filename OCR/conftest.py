"""Pytest bootstrap: make the project root importable from tests/.

The project is intentionally flat (no package), so test modules can import
`schema`, `mrz_parser`, ... directly once the root is on sys.path.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)