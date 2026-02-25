from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_PICTURE
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_NAME, CONF_SOURCES, DOMAIN

# Priority tiers for active source selection (highest to lowest)
_TIER1 = {MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING}
_TIER2 = {MediaPlayerState.PAUSED, MediaPlayerState.IDLE}
_TIER3 = {MediaPlayerState.ON}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    async_add_entities([CombinedMediaPlayer(entry)], update_before_add=False)


class CombinedMediaPlayer(MediaPlayerEntity):
    """Media player that combines multiple sources with configurable priority order.

    The first source in the list has the highest priority. Among sources in the
    same activity tier (playing > paused/idle > on), the one with the lower index
    wins. Controls are always forwarded to the current winning source.
    """

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_icon = "mdi:television-play"

    def __init__(self, entry: ConfigEntry) -> None:
        try:
            MediaPlayerEntity.__init__(self)
        except TypeError:
            pass
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._sources: list[str] = self._sources_from_entry(entry)
        self._attr_name: str = entry.data.get(CONF_NAME, "Combined Media Player")
        self._unsub: Any = None

    @staticmethod
    def _sources_from_entry(entry: ConfigEntry) -> list[str]:
        return list(
            entry.options.get(CONF_SOURCES)
            or entry.data.get(CONF_SOURCES, [])
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Refresh sources in case options were saved before this entity loaded
        self._sources = self._sources_from_entry(self._entry)
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
    def _handle_state_change(self, event) -> None:
        self.async_write_ha_state()

    # ── Active source resolution ───────────────────────────────────────────────

    def _active_state(self) -> State | None:
        """Return the highest-priority active source's State object."""
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                s = self.hass.states.get(sid)
                if s and _safe_state(s.state) and MediaPlayerState(s.state) in tier:
                    return s
        return None

    def _active_entity_id(self) -> str | None:
        """Return the entity_id of the highest-priority active source."""
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._sources:
                s = self.hass.states.get(sid)
                if s and _safe_state(s.state) and MediaPlayerState(s.state) in tier:
                    return sid
        return None

    # ── Availability & state ───────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Always available – combined player never shows unavailable."""
        return True

    @property
    def state(self) -> MediaPlayerState:
        active = self._active_state()
        if active is None:
            return MediaPlayerState.OFF
        src = active.state
        if src in {MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING}:
            return MediaPlayerState.PLAYING
        if src in {MediaPlayerState.PAUSED, MediaPlayerState.IDLE}:
            return MediaPlayerState.IDLE
        if src == MediaPlayerState.ON:
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    # ── Features ──────────────────────────────────────────────────────────────

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        active = self._active_state()
        if active is None:
            return MediaPlayerEntityFeature(0)
        try:
            return MediaPlayerEntityFeature(
                int(active.attributes.get("supported_features", 0))
            )
        except (TypeError, ValueError):
            return MediaPlayerEntityFeature(0)

    # ── Media attributes (proxied from active source) ──────────────────────────

    def _from_active(self, key: str, default: Any = None) -> Any:
        active = self._active_state()
        return active.attributes.get(key, default) if active else default

    @property
    def media_title(self) -> str | None:
        return self._from_active("media_title")

    @property
    def media_artist(self) -> str | None:
        return self._from_active("media_artist")

    @property
    def media_album_name(self) -> str | None:
        return self._from_active("media_album_name")

    @property
    def media_content_type(self) -> str | None:
        return self._from_active("media_content_type")

    @property
    def media_duration(self) -> int | None:
        return self._from_active("media_duration")

    @property
    def media_position(self) -> float | None:
        return self._from_active("media_position")

    @property
    def media_position_updated_at(self) -> Any:
        return self._from_active("media_position_updated_at")

    @property
    def media_series_title(self) -> str | None:
        return self._from_active("media_series_title")

    @property
    def media_season(self) -> str | None:
        return self._from_active("media_season")

    @property
    def media_episode(self) -> str | None:
        return self._from_active("media_episode")

    @property
    def app_name(self) -> str | None:
        return self._from_active("app_name")

    @property
    def volume_level(self) -> float | None:
        return self._from_active("volume_level")

    @property
    def is_volume_muted(self) -> bool | None:
        return self._from_active("is_volume_muted")

    @property
    def source(self) -> str | None:
        return self._from_active("source")

    @property
    def source_list(self) -> list[str] | None:
        return self._from_active("source_list")

    @property
    def shuffle(self) -> bool | None:
        return self._from_active("shuffle")

    @property
    def repeat(self) -> str | None:
        return self._from_active("repeat")

    # ── Cover art ─────────────────────────────────────────────────────────────

    @property
    def entity_picture(self) -> str | None:
        """Forward the active source's entity_picture.

        This transparently handles any image source:
        - Native cover art from PS5, AppleTV, etc.
        - media_cover_art-wrapped images (image/camera entities)
        """
        active = self._active_state()
        if active is None:
            return None
        return active.attributes.get(ATTR_ENTITY_PICTURE)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active_id = self._active_entity_id()
        return {
            "active_source": active_id,
            "sources": self._sources,
        }

    # ── Controls (forwarded to active source) ─────────────────────────────────

    async def _call_active(self, service: str, **kwargs: Any) -> None:
        target = self._active_entity_id()
        if target is None:
            return
        await self.hass.services.async_call(
            "media_player",
            service,
            {"entity_id": target, **kwargs},
            blocking=True,
        )

    async def async_media_play(self) -> None:
        await self._call_active("media_play")

    async def async_media_pause(self) -> None:
        await self._call_active("media_pause")

    async def async_media_stop(self) -> None:
        await self._call_active("media_stop")

    async def async_media_next_track(self) -> None:
        await self._call_active("media_next_track")

    async def async_media_previous_track(self) -> None:
        await self._call_active("media_previous_track")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._call_active("volume_set", volume_level=volume)

    async def async_volume_up(self) -> None:
        await self._call_active("volume_up")

    async def async_volume_down(self) -> None:
        await self._call_active("volume_down")

    async def async_mute_volume(self, mute: bool) -> None:
        await self._call_active("volume_mute", is_volume_muted=mute)

    async def async_media_seek(self, position: float) -> None:
        await self._call_active("media_seek", seek_position=position)

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        await self._call_active(
            "play_media",
            media_content_type=media_type,
            media_content_id=media_id,
            **kwargs,
        )

    async def async_select_source(self, source: str) -> None:
        await self._call_active("select_source", source=source)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._call_active("shuffle_set", shuffle=shuffle)

    async def async_set_repeat(self, repeat: str) -> None:
        await self._call_active("repeat_set", repeat=repeat)

    async def async_turn_on(self) -> None:
        await self._call_active("turn_on")

    async def async_turn_off(self) -> None:
        await self._call_active("turn_off")

    async def async_toggle(self) -> None:
        await self._call_active("toggle")


def _safe_state(raw: str) -> bool:
    """Return True if raw is a valid MediaPlayerState value."""
    try:
        MediaPlayerState(raw)
        return True
    except ValueError:
        return False
