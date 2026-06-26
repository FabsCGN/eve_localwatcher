"""The friendly set — who is NOT a threat and must be filtered out before any
enrichment call.

Reconstructs "blue / green / purple" from entities:
  purple = fleet        (esi-fleets.read_fleet.v1)
  green  = your corp     (own character's public affiliation, no scope)
  blue   = your alliance (own character's public affiliation, no scope)
         + manual blue corp/alliance ids from config
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set

from .esi import ESI


@dataclass
class FriendlySet:
    my_corp_id: Optional[int] = None
    my_alliance_id: Optional[int] = None
    fleet_ids: Set[int] = field(default_factory=set)
    blue_corp_ids: Set[int] = field(default_factory=set)
    blue_alliance_ids: Set[int] = field(default_factory=set)

    def is_friendly(self, char_id: Optional[int], corp_id: Optional[int],
                    alliance_id: Optional[int]) -> bool:
        if char_id is not None and char_id in self.fleet_ids:
            return True                       # purple — fleet
        if corp_id is not None and corp_id == self.my_corp_id:
            return True                       # green — own corp
        if alliance_id is not None and alliance_id == self.my_alliance_id:
            return True                       # blue — own alliance
        if corp_id is not None and corp_id in self.blue_corp_ids:
            return True
        if alliance_id is not None and alliance_id in self.blue_alliance_ids:
            return True
        return False


def build_friendly_set(esi: ESI, char_id: int, access_token: Optional[str],
                       blue_corp_ids=(), blue_alliance_ids=()) -> FriendlySet:
    """Assemble the friendly set from the logged-in character + live fleet.

    Corp/alliance (green/blue) come from the public affiliation and need no
    token; fleet (purple) is added only when a valid access token is given.
    """
    fs = FriendlySet(blue_corp_ids=set(blue_corp_ids),
                     blue_alliance_ids=set(blue_alliance_ids))
    aff = esi.affiliations([char_id]).get(char_id)
    if aff:
        fs.my_corp_id, fs.my_alliance_id, _ = aff
    if access_token:
        try:
            fs.fleet_ids = esi.fleet_member_ids(char_id, access_token)
        except Exception:
            fs.fleet_ids = set()    # token expired / not in a fleet → no purple
    return fs
