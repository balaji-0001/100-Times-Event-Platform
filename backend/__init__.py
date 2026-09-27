import sys
from pathlib import Path

_api_server_dir = Path(__file__).resolve().parent.parent / "artifacts" / "api-server"
_target_backend = _api_server_dir / "backend"

if str(_api_server_dir) not in sys.path:
    sys.path.insert(0, str(_api_server_dir))

__path__ = [str(_target_backend)]

