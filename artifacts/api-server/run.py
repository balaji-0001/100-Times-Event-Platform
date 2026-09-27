import os
import sys
from pathlib import Path

# Add artifacts/api-server to sys.path
api_server_dir = Path(__file__).resolve().parent
if str(api_server_dir) not in sys.path:
    sys.path.insert(0, str(api_server_dir))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.main:app', host='0.0.0.0', port=8000, reload=True)
