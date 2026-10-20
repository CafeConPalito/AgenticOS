"""PyInstaller entry point for the backend sidecar."""

import sys

if __name__ == "__main__":
    if "--knowledge-worker" in sys.argv:
        # The same executable, started by the backend as the knowledge library's worker.
        from agentic_os.services.knowledge.worker import serve

        serve()
    else:
        from agentic_os.__main__ import main

        main()
