"""Development server with hot-reload enabled.

Watches api/ and core/ directories for changes and auto-restarts.
Uses in-memory job store for development (jobs lost on restart).
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import uvicorn

def main():
    """Run development server with hot-reload."""
    port = int(os.getenv("PORT", "8000"))
    
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           ScoreForge API — Development Mode                    ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Hot-reload: ENABLED (watches api/ and core/)               ║")
    print("║  Job Store: MEMORY (jobs lost on restart)                    ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Host: http://0.0.0.0:{port}                             ║")
    print("║  Docs: http://0.0.0.0:{port}/docs                         ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("✓ Dev server starting with hot-reload...")
    print("✓ Changes to api/ or core/ will auto-restart the server")
    print()
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["api", "core"],
        log_level="info",
    )

if __name__ == "__main__":
    main()
