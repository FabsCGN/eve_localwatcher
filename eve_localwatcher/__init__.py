"""EVE Local Intel Scanner.

Passively watches a running EVE Online client's Local member list via screen
capture and raises an alarm the moment a non-friendly pilot appears — not just
when someone talks.

Detection is two-stage (see ``scanner.py``):
  * Stage 1 — OCR of the Local header count ("Local [8]"). Robust, catches
    pilots that appear below the visible area.
  * Stage 2 — pixel-sampling of the standing/colour tag icon to the left of
    each name, matched against a calibrated *friendly* whitelist. Anything not
    in the whitelist — including an empty/untagged slot — is a threat.
"""

__version__ = "2.0.0-beta.3"
