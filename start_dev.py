import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

root_dir = Path(__file__).resolve().parent
frontend_dir = root_dir / 'artifacts' / '100-times'

print('=' * 60)
print('  [100 TIMES] Starting Development Servers...')
print('=' * 60)

print('[1/2] Starting FastAPI Backend on port 8000...')
backend_proc = subprocess.Popen([sys.executable, 'main.py'], cwd=str(root_dir))

time.sleep(1)

print('[2/2] Starting React Vite Frontend on port 5174...')
frontend_proc = subprocess.Popen(
    ['npx', '--yes', 'vite', '--port', '5174', '--host', '0.0.0.0'],
    cwd=str(frontend_dir),
    shell=True,
)

time.sleep(2)

print('\n' + '=' * 60)
print('  [100 TIMES] Application is Live!')
print('  --------------------------------------------------------')
print('  * Frontend Website: http://localhost:5174')
print('  * Local Network:    http://127.0.0.1:5174')
print('  * Backend API:      http://127.0.0.1:8000')
print('  * Interactive Docs: http://127.0.0.1:8000/docs')
print('=' * 60 + '\n')

try:
    webbrowser.open('http://localhost:5174')
except Exception:
    pass

try:
    backend_proc.wait()
except KeyboardInterrupt:
    print('\nShutting down servers...')
    backend_proc.terminate()
    frontend_proc.terminate()
