"""Abstract victims feed adapter.

Concrete adapters live in:
    - local_dls.py          (Phase 3)
    - ransomware_live.py    (Phase 4 - subject to T&C compliance)

The active adapter is selected via config.ACTIVE_VICTIMS_ADAPTER.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import date
from typing import List, Optional


@dataclass
class Victim:
    name: str
    sector: str
    date: date
    source: str
    actor: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["date"] = self.date.isoformat() if isinstance(self.date, date) else self.date
        return d


class VictimsAdapter(ABC):
    """Common interface every victims feed must implement."""

    name: str = "abstract"

    @abstractmethod
    def get_victims(self, actor_name: str, since_date: date) -> List[Victim]:
        """Return victims attributed to `actor_name` from `since_date` onwards."""

    def attribution_notice(self) -> Optional[str]:
        """Optional attribution text included in exports (e.g. licensing clause)."""
        return None
