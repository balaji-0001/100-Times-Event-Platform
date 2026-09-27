"""100 TIMES FastAPI backend."""

import os
import sys
from pathlib import Path

# Ensure api-server directory is in sys.path
_parent_dir = str(Path(__file__).resolve().parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)