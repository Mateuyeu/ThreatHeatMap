"""LocalDLSAdapter - reads scraped DLS records from local JSON/CSV files.

Phase 1: stub implementation. The real loader lands in Phase 3, including
sector normalization through scoring/normalizer.py.
"""

from datetime import date
from pathlib import Path
from typing import List

from .victims_base import VictimsAdapter, Victim


class LocalDLSAdapter(VictimsAdapter):
    name = "local_dls"

    def __init__(self, dls_dir: str):
        self.dls_dir = Path(dls_dir)

    def get_victims(self, actor_name: str, since_date: date) -> List[Victim]:
        # Phase 3 will iterate the directory, parse JSON/CSV and normalize sectors.
        return []
