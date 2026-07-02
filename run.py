
import subprocess
import sys

# Start FastAPI backend
backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--reload"]
)

# Start Streamlit frontend (FIXED)
frontend = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "dashboard/streamlit_app.py"]
)

try:
    backend.wait()
    frontend.wait()
except KeyboardInterrupt:
    print("\nShutting down...")
    backend.terminate()
    frontend.terminate()