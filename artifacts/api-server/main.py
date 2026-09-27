import os
import sys
from pathlib import Path

_API_SERVER_DIR = Path(__file__).resolve().parent
if str(_API_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_API_SERVER_DIR))

# Expose 'app' for uvicorn main:app --reload
from backend.main import app

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
