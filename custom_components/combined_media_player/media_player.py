from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_AUDIO_SOURCES, CONF_NAME, CONF_SOURCES, DOMAIN

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
        self._attr_unique_id = entry.unique_id
        self._sources: list[str] = self._sources_from_entry(entry)
        self._audio_sources: list[str] = self._audio_sources_from_entry(entry)
        self._attr_name: str = (
            entry.options.get(CONF_NAME)
            or entry.data.get(CONF_NAME, "Combined Media Player")
        )
        self._unsub: Any = None
        self._attr_entity_picture: str | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._attr_name,
            manufacturer="Combined Media Player",
            model="Virtual Media Player",
        )

    @staticmethod
    def _sources_from_entry(entry: ConfigEntry) -> list[str]:
        return list(
            entry.options.get(CONF_SOURCES)
            or entry.data.get(CONF_SOURCES, [])
        )

    @staticmethod
    def _audio_sources_from_entry(entry: ConfigEntry) -> list[str]:
        return list(
            entry.options.get(CONF_AUDIO_SOURCES)
            or entry.data.get(CONF_AUDIO_SOURCES, [])
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Refresh sources in case options were saved before this entity loaded
        self._sources = self._sources_from_entry(self._entry)
        self._audio_sources = self._audio_sources_from_entry(self._entry)
        # Seed entity_picture from the already-known active source state
        self._attr_entity_picture = self._from_active("entity_picture")
        # Track all unique entity IDs (audio sources may not be in main sources list)
        all_tracked = list(dict.fromkeys(self._sources + self._audio_sources))
        if all_tracked:
            self._unsub = async_track_state_change_event(
                self.hass,
                all_tracked,
                self._handle_state_change,
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_state_change(self, event) -> None:
        self._attr_entity_picture = self._from_active("entity_picture")
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

    def _active_audio_entity_id(self) -> str | None:
        """Return the highest-priority active audio source entity_id, or None.

        Audio sources are a subset of sources designated to receive control
        commands (volume, play/pause, skip) when they are active. This lets a
        display-only source (e.g. a gaming PC) win for cover/state while audio
        controls still reach the real playback device (e.g. HomePods).
        """
        if not self._audio_sources:
            return None
        for tier in (_TIER1, _TIER2, _TIER3):
            for sid in self._audio_sources:
                s = self.hass.states.get(sid)
                if s and _safe_state(s.state) and MediaPlayerState(s.state) in tier:
                    return sid
        return None

    def _control_state(self) -> State | None:
        """Return the State used for control-related attributes.

        Prefers the active audio source (if configured and active) so that
        volume level, supported features, shuffle, and repeat reflect the
        device that will actually receive commands. Falls back to the normal
        display-priority source when no audio source is active.
        """
        audio_id = self._active_audio_entity_id()
        if audio_id:
            return self.hass.states.get(audio_id)
        return self._active_state()

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
        ctrl = self._control_state()
        if ctrl is None:
            return MediaPlayerEntityFeature(0)
        try:
            features = MediaPlayerEntityFeature(
                int(ctrl.attributes.get("supported_features", 0))
            )
        except (TypeError, ValueError):
            return MediaPlayerEntityFeature(0)
        # BROWSE_MEDIA is a content-library capability, not a hardware capability.
        # Expose it whenever *any* configured source supports it so the browser
        # remains accessible regardless of which source is currently active or
        # whether the audio/control target (e.g. HomePods) supports browsing.
        browse_bit = int(MediaPlayerEntityFeature.BROWSE_MEDIA)
        for sid in self._sources + self._audio_sources:
            s = self.hass.states.get(sid)
            if s is None:
                continue
            try:
                if int(s.attributes.get("supported_features", 0)) & browse_bit:
                    features |= MediaPlayerEntityFeature.BROWSE_MEDIA
                    break
            except (TypeError, ValueError):
                continue
        return features

    # ── Media attributes (proxied from active source) ──────────────────────────

    def _from_active(self, key: str, default: Any = None) -> Any:
        active = self._active_state()
        return active.attributes.get(key, default) if active else default

    def _from_control(self, key: str, default: Any = None) -> Any:
        """Read an attribute from the control target (audio source preferred)."""
        ctrl = self._control_state()
        return ctrl.attributes.get(key, default) if ctrl else default

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
        return self._from_control("volume_level")

    @property
    def is_volume_muted(self) -> bool | None:
        return self._from_control("is_volume_muted")

    @property
    def source(self) -> str | None:
        return self._from_control("source")

    @property
    def source_list(self) -> list[str] | None:
        return self._from_control("source_list")

    @property
    def shuffle(self) -> bool | None:
        return self._from_control("shuffle")

    @property
    def repeat(self) -> str | None:
        return self._from_control("repeat")

    # ── Cover art ─────────────────────────────────────────────────────────────

    @property
    def media_image_url(self) -> str | None:
        """Return cover art URL.

        Only returns directly accessible URLs (http/https). HA-internal proxy
        paths from entity_picture are intentionally excluded: they contain
        session tokens and cannot be followed by external consumers like Music
        Assistant. When only a proxied URL is available, we return None so that
        HA creates its own proxy for this entity via async_get_media_image().
        """
        active = self._active_state()
        if active is None:
            return None
        url = active.attributes.get("media_image_url")
        if url and url.startswith("http"):
            return url
        # entity_picture is a session-scoped HA-internal path – not usable externally.
        # Fall back to None; async_get_media_image() will fetch via the image entity.
        return None

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Fetch cover art from the paired CombinedCoverImage entity.

        image.py handles caching, entity_picture fallback, and last-known-good
        persistence.  Delegating here avoids duplicating that logic and ensures
        the media-player card and the image entity always show the same art.
        """
        er = async_get_entity_registry(self.hass)
        image_entity_id = er.async_get_entity_id(
            "image", DOMAIN, f"{self._entry.unique_id}_cover"
        )
        if image_entity_id:
            image_component = self.hass.data.get("image")
            if image_component is not None and hasattr(image_component, "get_entity"):
                entity = image_component.get_entity(image_entity_id)
                if entity is not None:
                    try:
                        data = await entity.async_image()
                        if data:
                            return data, getattr(entity, "content_type", None) or "image/jpeg"
                    except Exception:
                        pass
        return None, None

    def _browse_entity_id(self) -> str | None:
        """Return the entity_id of the best source to delegate media browsing to.

        Selection order:
        1. The currently active display source, if it supports BROWSE_MEDIA.
        2. The currently active audio source, if it supports BROWSE_MEDIA.
        3. Any source (display or audio, regardless of playback state) that
           supports BROWSE_MEDIA – first match wins.
        """
        browse_bit = int(MediaPlayerEntityFeature.BROWSE_MEDIA)

        def _supports_browse(entity_id: str) -> bool:
            s = self.hass.states.get(entity_id)
            if s is None:
                return False
            try:
                return bool(int(s.attributes.get("supported_features", 0)) & browse_bit)
            except (TypeError, ValueError):
                return False

        # Prefer whichever source is currently active and can browse
        for candidate in (self._active_entity_id(), self._active_audio_entity_id()):
            if candidate and _supports_browse(candidate):
                return candidate

        # Fall back to any configured source that supports browsing
        seen: set[str] = set()
        for sid in self._sources + self._audio_sources:
            if sid not in seen:
                seen.add(sid)
                if _supports_browse(sid):
                    return sid

        return None

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Delegate media browsing to the best available source entity."""
        browse_id = self._browse_entity_id()
        if not browse_id:
            raise BrowseError("No source with BROWSE_MEDIA support found")
        component = self.hass.data.get("media_player")
        if component is None or not hasattr(component, "get_entity"):
            raise BrowseError("Media player component not available")
        entity = component.get_entity(browse_id)
        if entity is None:
            raise BrowseError(f"Source entity {browse_id!r} not found")
        return await entity.async_browse_media(media_content_type, media_content_id)

    @property
    def media_image_remotely_accessible(self) -> bool:
        """Return True only when the source exposes a direct CDN URL."""
        active = self._active_state()
        if active is None:
            return False
        url = active.attributes.get("media_image_url", "")
        return bool(url and url.startswith("http") and self._from_active("media_image_remotely_accessible", False))

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active_id = self._active_entity_id()
        audio_id = self._active_audio_entity_id()
        attrs: dict[str, Any] = {
            "active_source": active_id,
            "sources": self._sources,
        }
        if self._audio_sources:
            attrs["active_audio_source"] = audio_id
            attrs["audio_sources"] = self._audio_sources
        return attrs

    # ── Controls (forwarded to active source) ─────────────────────────────────

    async def _call_active(self, service: str, **kwargs: Any) -> None:
        # Prefer the active audio source for commands; fall back to display source.
        target = self._active_audio_entity_id() or self._active_entity_id()
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
