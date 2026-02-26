"""Test configuration to ensure project package imports work.

This adds the repository root to sys.path so `import station` resolves
when running tests from the repo root.
"""
import os
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATION_SRC = os.path.join(REPO_ROOT, "station")

# Prefer importing modules directly from the station package root (to avoid
# triggering station.__init__ which imports the FastAPI app).
for p in (STATION_SRC, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
