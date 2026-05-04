"""RansomwareLiveAdapter - ransomware.live public API connector.

Licensing safeguards (per project requirements):
    - Usage flag in config.RANSOMWARE_LIVE_USAGE: "evaluation" | "authorized_commercial" | "disabled"
    - License notice emitted on instantiation (logging + console banner)
    - Disabled state raises an explicit error on first call
    - Exports issued via this adapter must carry the attribution clause
      (see attribution_notice()).

Phase 1 status: scaffolding only. Phase 4 implements the real HTTP calls.
"""

import logging
from datetime import date
from typing import List

from .victims_base import VictimsAdapter, Victim

LOGGER = logging.getLogger(__name__)

LICENSE_NOTICE_TEMPLATE = (
    "[LICENSE NOTICE] ransomware.live data is licensed for non-commercial use only "
    "(T&C section 2.1). Current usage flag: {flag}. Commercial use requires written "
    "authorization from the data owner."
)
ATTRIBUTION_TEXT = "Source: Ransomware.live (https://www.ransomware.live)"

VALID_USAGE_FLAGS = {"evaluation", "authorized_commercial", "disabled"}


class RansomwareLiveDisabledError(RuntimeError):
    pass


class RansomwareLiveAdapter(VictimsAdapter):
    name = "ransomware_live"

    def __init__(self, usage_flag: str, api_base: str = "https://api.ransomware.live"):
        if usage_flag not in VALID_USAGE_FLAGS:
            raise ValueError(
                f"Invalid RANSOMWARE_LIVE_USAGE='{usage_flag}'. "
                f"Expected one of {sorted(VALID_USAGE_FLAGS)}."
            )
        self.usage_flag = usage_flag
        self.api_base = api_base
        self._announce_license()

    def _announce_license(self):
        message = LICENSE_NOTICE_TEMPLATE.format(flag=self.usage_flag)
        LOGGER.info(message)
        banner = "=" * 78
        print(banner)
        print(message)
        print(banner)

    def get_victims(self, actor_name: str, since_date: date) -> List[Victim]:
        if self.usage_flag == "disabled":
            raise RansomwareLiveDisabledError(
                "ransomware.live connector is disabled "
                "(RANSOMWARE_LIVE_USAGE='disabled'). Set the flag to 'evaluation' or "
                "'authorized_commercial' to enable it."
            )
        # Phase 4: real HTTP calls + caching.
        return []

    def attribution_notice(self):
        return ATTRIBUTION_TEXT
