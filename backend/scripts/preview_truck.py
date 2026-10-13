"""Checkout CLI bootstrap; no engineering logic or source authority bypass."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cold_storage.modules.layout.application.truck_preview import main  # noqa: E402

if __name__ == "__main__":
    main()
