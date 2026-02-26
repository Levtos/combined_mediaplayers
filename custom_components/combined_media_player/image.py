from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_PICTURE
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util, slugify

from .const import CONF_SOURCES
from .media_player import _TIER1, _TIER2, _TIER3, _safe_state


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    async_add_entities([CombinedCoverImage(hass, entry)], update_before_add=False)


class CombinedCoverImage(ImageEntity):
    """Image entity exposing cover art URL from the active combined source."""

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

    def _get_cover_url(self) -> str | None:
        active = self._active_state()
        if active is None:
            return None
        return active.attributes.get(ATTR_ENTITY_PICTURE)

    def _refresh_image_url(self) -> None:
        """Update _attr_image_url and bump image_last_updated when the URL changed."""
        new_url = self._get_cover_url()
        # _attr_image_url starts as UNDEFINED (class default); treat any change as new
        if new_url != getattr(self, "_attr_image_url", None):
            self._attr_image_url = new_url
            self._attr_image_last_updated = dt_util.utcnow()

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
            ATTR_ENTITY_PICTURE: active.attributes.get(ATTR_ENTITY_PICTURE)
            if active
            else None,
            "active_source": active.entity_id if active else None,
            "active_source_name": (
                active.attributes.get("friendly_name") or active.entity_id
            )
            if active
            else None,
        }
