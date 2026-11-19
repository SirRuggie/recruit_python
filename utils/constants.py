import os
import hikari
from dotenv import load_dotenv

load_dotenv()

# Channel where recruitment posts go. Set RECRUITMENT_CHANNEL_ID in .env to change it.
RECRUITMENT_CHANNEL_ID = int(os.getenv("RECRUITMENT_CHANNEL_ID") or 1144471630614114454)

RED_ACCENT = hikari.Color.from_hex_code("#AA0000")
GOLD_ACCENT = hikari.Color.from_hex_code("FFD700")
BLUE_ACCENT = hikari.Color.from_hex_code("0066FF")
GREEN_ACCENT = hikari.Color.from_hex_code("00B237")
MAGENTA_ACCENT = hikari.Color.from_hex_code("FF00FF")
CYAN_ACCENT = hikari.Color.from_hex_code("00FFFF")

# Clan Information
CLAN_TYPES = ["Tactical", "Flexible Fun", "FWA", "CWL"]
TH_LEVELS = [str(i) for i in range(3, 18)]


# FWA Images
FWA_WAR_BASE = {}

FWA_ACTIVE_WAR_BASE = {}