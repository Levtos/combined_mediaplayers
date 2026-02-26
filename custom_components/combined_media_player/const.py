from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "combined_media_player"

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.IMAGE]

CONF_NAME = "name"
CONF_SOURCES = "sources"
