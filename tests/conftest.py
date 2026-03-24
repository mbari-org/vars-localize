import sys
from pathlib import Path


# Ensure test runs can import package modules directly from src/.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
