from __future__ import annotations

import logging

import aiohttp
from typing import Any

_LOGGER = logging.getLogger(__name__)

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

# Used only for fingerprinting (cache-busting); entity_picture changes whenever
# the cache key changes, which happens when media_image_url changes.
_FINGERPRINT_ATTR = ATTR_ENTITY_PICTURE

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

        Uses entity_picture which contains a cache key derived from media_image_url,
        so it changes automatically whenever the cover art changes.
        """
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                state = self.hass.states.get(sid)
                if not (state and _safe_state(state.state) and state.state in tier):
                    continue
                url = state.attributes.get(_FINGERPRINT_ATTR)
                if url:
                    return f"{sid}:{url}"
        return None

    def _refresh_image_url(self) -> None:
        """Bump image_last_updated when the image fingerprint changes."""
        fp = self._image_fingerprint()
        if fp != getattr(self, "_cached_fingerprint", None):
            self._cached_fingerprint: str | None = fp
            self._attr_image_last_updated = dt_util.utcnow()

    async def _get_entity_image(self, entity_id: str) -> bytes | None:
        """Get image bytes by calling async_get_media_image() on the entity object.

        This is the same path HA's media_player proxy uses internally, so it
        handles Music Assistant auth, custom URL schemes, pyatv, etc. correctly
        without needing to know what type of integration the source uses.
        Returns None if the entity object is not accessible or has no image.
        """
        mp_component = self.hass.data.get("media_player")
        if mp_component is None or not hasattr(mp_component, "get_entity"):
            _LOGGER.debug(
                "%s: media_player EntityComponent not available, falling back to URL fetch",
                entity_id,
            )
            return None
        entity = mp_component.get_entity(entity_id)
        if entity is None:
            _LOGGER.debug("%s: entity object not found in component", entity_id)
            return None
        if not hasattr(entity, "async_get_media_image"):
            _LOGGER.debug("%s: entity has no async_get_media_image()", entity_id)
            return None
        try:
            image_data, content_type = await entity.async_get_media_image()
            if image_data:
                self._attr_content_type = content_type or "image/jpeg"
                return image_data
            _LOGGER.debug("%s: async_get_media_image() returned no data", entity_id)
        except Exception as exc:
            _LOGGER.debug("%s: async_get_media_image() failed: %s", entity_id, exc)
        return None

    async def _fetch_url(
        self, session: aiohttp.ClientSession, url: str
    ) -> bytes | None:
        """Fallback: fetch image bytes from a URL, resolving HA-relative paths."""
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
           a. Call async_get_media_image() on the entity object directly –
              same internal path as HA's media_player proxy, handles Music
              Assistant auth, pyatv, etc. transparently.
           b. Fallback: fetch entity_picture URL directly (CDN URL or HA proxy
              URL with embedded token).
        2. If the primary source fails (e.g. pyatv returns "Artwork not
           present"), fall through to the next active source so a playing
           HomePod can supply artwork when Apple TV has none.
        """
        session = async_get_clientsession(self.hass)
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                state = self.hass.states.get(sid)
                if not (state and _safe_state(state.state) and state.state in tier):
                    continue

                # Primary: delegate to the source entity's own implementation.
                # Each integration (Music Assistant, Apple TV, PS5, …) implements
                # async_get_media_image() for its specific protocol/auth needs.
                # This is the same internal path HA's media_player proxy uses.
                image = await self._get_entity_image(sid)
                if image is not None:
                    _LOGGER.debug("%s: image retrieved via async_get_media_image()", sid)
                    return image

                # Fallback: fetch entity_picture URL directly.
                # Covers CDN URLs (remotely accessible) and HA proxy URLs
                # (embedded token acts as auth).
                url = state.attributes.get(ATTR_ENTITY_PICTURE)
                if url:
                    image = await self._fetch_url(session, url)
                    if image is not None:
                        _LOGGER.debug("%s: image retrieved via entity_picture URL", sid)
                        return image

                _LOGGER.debug(
                    "%s: no image available, trying next source in priority chain", sid
                )
        _LOGGER.debug("No active source could provide a cover image")
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
