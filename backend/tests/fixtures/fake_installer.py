"""A CLI's installer (phase 23): prints its steps, drops the CLI in a folder and ends with the
exit code given, like the official PowerShell scripts.

Usage: python fake_installer.py <folder> <name> <exit code>
"""

import sys
from pathlib import Path

folder, name, code = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
print("Descargando…", flush=True)
if code == 0:
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / (name + (".exe" if sys.platform == "win32" else ""))
    program.write_bytes(b"")
    program.chmod(0o755)
    print("Instalación completa", flush=True)
else:
    print("Fatal: Failed to download release manifest. Network or DNS issue?", flush=True)
sys.exit(code)
