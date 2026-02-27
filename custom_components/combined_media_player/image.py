from __future__ import annotations

import aiohttp
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_PICTURE
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.network import get_url as ha_get_url
from homeassistant.util import dt as dt_util, slugify

from .const import CONF_SOURCES, DOMAIN
from .media_player import _TIER1, _TIER2, _TIER3, _safe_state

# Attributes to check per source, in preference order:
# 1. media_image_url – direct CDN/https URL (Spotify, Apple Music, …); only
#    present in state attributes when media_image_remotely_accessible is True.
# 2. entity_picture  – HA-proxied URL (/api/media_player_proxy/…).
_IMAGE_ATTRS = ("media_image_url", ATTR_ENTITY_PICTURE)

_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    async_add_entities([CombinedCoverImage(hass, entry)], update_before_add=False)


class CombinedCoverImage(ImageEntity):
    """Image entity exposing cover art from the active combined source."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:image"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass)  # initialises access_tokens, HTTP client, etc.
        self._entry = entry
        self._sources: list[str] = self._sources_from_entry(entry)
        self._attr_unique_id = f"{entry.unique_id}_cover"
        self._attr_name = f"{entry.title} Cover"
        self._attr_suggested_object_id = (
            f"{slugify(entry.unique_id or entry.entry_id)}_cover"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )
        self._unsub: Any = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sources_from_entry(entry: ConfigEntry) -> list[str]:
        return list(
            entry.options.get(CONF_SOURCES) or entry.data.get(CONF_SOURCES, [])
        )

    def _active_state(self) -> State | None:
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                state = self.hass.states.get(sid)
                if state and _safe_state(state.state) and state.state in tier:
                    return state
        return None

    def _image_fingerprint(self) -> str | None:
        """Return a string that changes whenever the displayed image should change.

        Considers the primary active source and its image URL so that
        image_last_updated is bumped correctly for cache-busting.
        """
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                state = self.hass.states.get(sid)
                if not (state and _safe_state(state.state) and state.state in tier):
                    continue
                for attr in _IMAGE_ATTRS:
                    url = state.attributes.get(attr)
                    if url:
                        return f"{sid}:{url}"
        return None

    def _refresh_image_url(self) -> None:
        """Bump image_last_updated when the image fingerprint changes."""
        fp = self._image_fingerprint()
        if fp != getattr(self, "_cached_fingerprint", None):
            self._cached_fingerprint: str | None = fp
            self._attr_image_last_updated = dt_util.utcnow()

    async def _fetch_image(
        self, session: aiohttp.ClientSession, url: str
    ) -> bytes | None:
        """Fetch image bytes from *url*, resolving HA-relative paths.

        Returns None on any error so the caller can try the next candidate.
        """
        if url.startswith("/"):
            base = None
            for kw in (
                {"allow_ip": True, "prefer_external": False},
                {"allow_ip": True, "prefer_external": True},
            ):
                try:
                    base = ha_get_url(self.hass, **kw)
                    break
                except Exception:
                    pass
            url = f"{base or 'http://127.0.0.1:8123'}{url}"
        try:
            async with session.get(url, timeout=_FETCH_TIMEOUT) as resp:
                if resp.status == 200:
                    self._attr_content_type = resp.content_type or "image/jpeg"
                    return await resp.read()
        except Exception:
            pass
        return None

    async def async_image(self) -> bytes | None:
        """Return cover art bytes.

        Strategy (most-reliable first):
        1. For each active source (highest tier / priority first):
           a. Try ``media_image_url`` – direct CDN URL present when the image
              is remotely accessible (HomePod + Spotify/Apple Music, etc.).
           b. Try ``entity_picture`` – HA-proxied URL that fetches artwork
              through the integration (Apple TV via pyatv, PS5, …).
        2. If the primary source fails (e.g. pyatv returns "Artwork not
           present"), fall through to the next active source.  This means a
           playing HomePod can supply the artwork even when an Apple TV is
           technically the highest-priority source but has no artwork.
        """
        session = async_get_clientsession(self.hass)
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                state = self.hass.states.get(sid)
                if not (state and _safe_state(state.state) and state.state in tier):
                    continue
                for attr in _IMAGE_ATTRS:
                    url = state.attributes.get(attr)
                    if not url:
                        continue
                    image = await self._fetch_image(session, url)
                    if image is not None:
                        return image
        return None

    # ------------------------------------------------------------------
    # Life cycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._sources = self._sources_from_entry(self._entry)
        self._refresh_image_url()
        if self._sources:
            self._unsub = async_track_state_change_event(
                self.hass,
                self._sources,
                self._handle_state_change,
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_state_change(self, _event) -> None:
        self._refresh_image_url()
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # State / attributes
    # ------------------------------------------------------------------
    # NOTE: ImageEntity.state is @final and returns image_last_updated.isoformat().
    # We surface the active source name as an extra attribute instead.

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active = self._active_state()
        return {
            "active_source": active.entity_id if active else None,
            "active_source_name": (
                active.attributes.get("friendly_name") or active.entity_id
            )
            if active
            else None,
        }
