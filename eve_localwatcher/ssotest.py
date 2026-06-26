"""Verify the EVE SSO login + fleet read end-to-end.

    python -m eve_localwatcher.ssotest

Opens the browser, logs you in, stores the refresh token in the config, then
prints your character, corp/alliance and current fleet size.
"""
from __future__ import annotations

from . import esi as esimod
from . import friendly, sso
from .config import Config


def main() -> None:
    cfg = Config.load()
    if not cfg.sso_client_id:
        print("Keine sso_client_id in der Config. Erst die Client ID eintragen.")
        return

    print("Öffne Browser zum EVE-Login …")
    tokens, info = sso.login(cfg.sso_client_id)
    access = tokens["access_token"]
    char_id = info["character_id"]

    # persist for reuse
    cfg.sso_refresh_token = tokens.get("refresh_token")
    cfg.sso_character_id = char_id
    cfg.sso_character_name = info.get("name")
    cfg.save()

    esi = esimod.ESI(cfg.zkill_contact)
    fs = friendly.build_friendly_set(esi, char_id, access,
                                     cfg.blue_corp_ids, cfg.blue_alliance_ids)
    ent = esi.names_for_ids([i for i in (fs.my_corp_id, fs.my_alliance_id) if i])

    print(f"\n✓ Eingeloggt als {info.get('name')} (ID {char_id})")
    print(f"  Corp:     {ent.get(fs.my_corp_id, fs.my_corp_id)}")
    print(f"  Allianz:  {ent.get(fs.my_alliance_id, fs.my_alliance_id)}")
    print(f"  Fleet:    {len(fs.fleet_ids)} Mitglieder erkannt")
    print(f"  Scopes:   {info.get('scopes')}")
    print("\nRefresh-Token gespeichert — künftige Checks brauchen kein erneutes Login.")


if __name__ == "__main__":
    main()
