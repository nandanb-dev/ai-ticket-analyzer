import sys
import uvicorn

sys.dont_write_bytecode = True

if __name__ == "__main__":
    # Run from the backend/ directory: python run.py
    # Swagger UI → http://localhost:8000/docs
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
