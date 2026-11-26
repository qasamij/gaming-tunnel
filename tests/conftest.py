import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("PANEL_DATA", str(Path(tempfile.gettempdir()) / "1mobile-tests"))
