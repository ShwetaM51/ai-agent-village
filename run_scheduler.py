"""Run the scheduler as a standalone process.

Usage:
    python run_scheduler.py

Run this in a separate terminal from the FastAPI app. They share the
database, but they're independent processes — which is exactly how this
would deploy in production (one or more worker processes, plus the API).
"""
from scheduler import run_forever

if __name__ == "__main__":
    run_forever()
