import sys
from pathlib import Path

import uvicorn

sys.dont_write_bytecode = True

backend_dir = Path(__file__).resolve().parent
project_root = backend_dir.parent
frontend_dir = project_root / "frontend"

if __name__ == "__main__":
    # Run from the backend/ directory: python run.py
    # Swagger UI → http://localhost:8000/docs
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(backend_dir), str(frontend_dir)],
        reload_excludes=[".venv/*", "**/.venv/*", "__pycache__/*", "**/__pycache__/*"],
    )
