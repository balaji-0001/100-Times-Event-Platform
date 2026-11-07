import os
import subprocess
import winreg

candidates = [
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
    r"C:\Program Files\Docker\Docker\docker.exe",
    r"C:\Program Files\Docker\Docker\resources\docker.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Docker\Docker\resources\bin\docker.exe"),
]

for c in candidates:
    if os.path.exists(c):
        print("Found Docker at:", c)

# Check registry
for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
    try:
        with winreg.OpenKey(root, r"Environment") as key:
            path, _ = winreg.QueryValueEx(key, "Path")
            for p in path.split(";"):
                if "docker" in p.lower():
                    print("Registry PATH has:", p)
    except Exception:
        pass

# Check system PATH
try:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
        path, _ = winreg.QueryValueEx(key, "Path")
        for p in path.split(";"):
            if "docker" in p.lower():
                print("System PATH has:", p)
except Exception as e:
    print("Error reading system path:", e)
