"""
player_name_store.py — Module-level singleton for player session data.
Stores name, JWT token, and guest status across the session.
"""

name:     str  = "GUEST"
token:    str  = ""        # JWT token — empty if guest
is_guest: bool = True      # True if not logged in