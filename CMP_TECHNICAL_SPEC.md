# Combined Media Player (CMP) — Technical Specification

> Generated for porting CMP functionality into Media Art Wrapper.

---

## 1. Architecture Overview

CMP is a Home Assistant custom integration (`domain: combined_media_player`) that creates a **virtual media player entity** by aggregating multiple real media player entities with priority-based source selection. It registers two platforms: `media_player` and `image`.

### File Structure

| File | Role |
|---|---|
| `__init__.py` | Entry setup/teardown, update listener |
| `const.py` | Domain name, platform list, config key constants |
| `config_flow.py` | UI-based ConfigFlow + OptionsFlow |
| `media_player.py` | `CombinedMediaPlayer` entity (~490 lines) |
| `image.py` | `CombinedCoverImage` entity with 2-layer cache (~541 lines) |
| `manifest.json` | Integration metadata (v1.6.0, `local_push` type) |

### Integration Lifecycle

```
async_setup_entry(hass, entry):
    hass.data[DOMAIN][entry.entry_id] = entry
    entry.add_update_listener(_async_update_listener)
    forward_entry_setups(entry, [MEDIA_PLAYER, IMAGE])

_async_update_listener(hass, entry):
    hass.config_entries.async_reload(entry.entry_id)  # full tear-down + re-setup on options change
```

There is **no DataUpdateCoordinator**. State tracking is entirely event-driven via `async_track_state_change_event`. There is no polling (`_attr_should_poll = False`).

### Device Registry

Both entities share a single device via `DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})`.

---

## 2. Configuration (config_flow.py)

### Initial Setup (`async_step_user`)

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Display name for the combined player |
| `sources` | `list[str]` | yes | Ordered list of `media_player.*` entity IDs (index 0 = highest priority) |
| `audio_sources` | `list[str]` | no | Subset of players that receive control commands |

**Unique ID**: `combined_{name_lower_underscored}` — duplicate names are rejected.

All three fields are stored in `entry.data`.

### Options Flow (`async_step_init`)

Uses a **slot-based UI** (8 dropdown slots) instead of a multi-select, to make priority ordering explicit and visible. Slots are converted to/from the ordered source list:

- `_providers_to_slots(sources)` → `{slot_1: "media_player.foo", slot_2: "", ...}`
- `_slots_to_providers(form_data)` → `["media_player.foo"]` (empties and duplicates dropped)

On save, the entry title is updated if the name changed, and the options are persisted. The update listener triggers a full `async_reload`, which tears down and re-creates both entities with the new config.

**Source resolution priority in entity code**: `entry.options` takes precedence over `entry.data` (options are set after the first reconfigure).

---

## 3. Priority Logic — Active Source Resolution

Defined in `media_player.py`, lines 20–23 and methods `_active_state()` / `_active_entity_id()`.

### Tier Definitions

```python
_TIER1 = {MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING}   # highest
_TIER2 = {MediaPlayerState.PAUSED, MediaPlayerState.IDLE}
_TIER3 = {MediaPlayerState.ON}
# States OFF, UNAVAILABLE, UNKNOWN → ignored (source is inactive)
```

### Algorithm (`_active_state()` / `_active_entity_id()`)

```
for tier in [TIER1, TIER2, TIER3]:
    for sid in self._sources:          # ordered by config priority (index 0 = highest)
        state = hass.states.get(sid)
        if state is valid AND state.state is in tier:
            return state               # FIRST match wins
return None                            # no source is active
```

Key behavior:
- **Tier beats index**: A source in TIER1 (playing) always wins over a source in TIER2 (paused), regardless of their index positions.
- **Index breaks ties within a tier**: Among sources in the same tier, the one with the lower index (higher config priority) wins.
- **State validation**: `_safe_state(raw)` attempts `MediaPlayerState(raw)` and returns `False` on `ValueError`, preventing crashes on unexpected state strings.

### State Mapping to Combined Entity

| Active source state | Combined entity state |
|---|---|
| `PLAYING` or `BUFFERING` | `PLAYING` |
| `PAUSED` or `IDLE` | `IDLE` |
| `ON` | `ON` |
| No active source (all off/unavailable) | `OFF` |

The combined entity is **always available** (`available` property returns `True`). It shows `OFF` rather than `UNAVAILABLE` when no sources are active.

---

## 4. Audio Sources — Dual-Source Mode

### Purpose

The `audio_sources` config option enables a **split display/control** pattern. This addresses scenarios where:
- A display device (e.g., gaming PC, smart TV) should provide media metadata and cover art
- A separate audio device (e.g., HomePods, soundbar) should receive playback/volume commands

### How It Works

There are three resolution methods, each with a distinct role:

| Method | Source list | Purpose |
|---|---|---|
| `_active_state()` | `self._sources` (display) | Media attributes, cover art, state display |
| `_active_entity_id()` | `self._sources` (display) | Identify the display winner |
| `_active_audio_entity_id()` | `self._audio_sources` (audio) | Identify the control target |
| `_control_state()` | audio preferred, display fallback | Volume, features, shuffle, repeat |

`_active_audio_entity_id()` uses the **same tier algorithm** as `_active_entity_id()`, but iterates over `self._audio_sources` instead of `self._sources`.

`_control_state()` logic:
```python
def _control_state(self):
    audio_id = self._active_audio_entity_id()
    if audio_id:
        return hass.states.get(audio_id)
    return self._active_state()   # fallback to display source
```

### Attribute Split

| Attribute category | Source | Method |
|---|---|---|
| `media_title`, `media_artist`, `media_album_name`, `media_content_type`, `media_duration`, `media_position`, `media_position_updated_at`, `media_series_title`, `media_season`, `media_episode`, `app_name` | Display source | `_from_active(key)` |
| `volume_level`, `is_volume_muted`, `source`, `source_list`, `shuffle`, `repeat` | Control source (audio preferred) | `_from_control(key)` |
| `supported_features` | Control source (audio preferred) | `_control_state()` |

### Audio Sources Not in Main Sources

Audio sources can be entities that are NOT in the main `sources` list. The lifecycle tracking handles this:
```python
all_tracked = list(dict.fromkeys(self._sources + self._audio_sources))  # deduplicated, order-preserved
```

### When No Audio Sources Are Configured

If `audio_sources` is empty (the default), `_active_audio_entity_id()` returns `None`, and all attribute reads and commands fall through to the display source. The integration behaves as a simple priority-based aggregator.

---

## 5. State & Attribute Propagation

### Attributes from Active Display Source (`_from_active`)

These are read directly from `self._active_state().attributes`:

- `media_title`
- `media_artist`
- `media_album_name`
- `media_content_type`
- `media_duration`
- `media_position`
- `media_position_updated_at`
- `media_series_title`
- `media_season`
- `media_episode`
- `app_name`

### Attributes from Control Source (`_from_control`)

These are read from `self._control_state().attributes` (audio source preferred):

- `volume_level`
- `is_volume_muted`
- `source`
- `source_list`
- `shuffle`
- `repeat`

### Supported Features

Read from control source with special `BROWSE_MEDIA` handling:

```python
@property
def supported_features(self):
    features = control_state.attributes["supported_features"]

    # BROWSE_MEDIA: enabled if ANY configured source (display OR audio) supports it
    for sid in self._sources + self._audio_sources:
        if source_supports_browse(sid):
            features |= BROWSE_MEDIA
            break
    return features
```

This ensures the media browser remains accessible even when the active control target (e.g., HomePods) doesn't support browsing but another source (e.g., Plex) does.

### Cover Art

`media_image_url` only returns absolute HTTP(S) URLs from the active display source. HA-internal proxy paths (entity_picture with auth tokens) are intentionally excluded — the entity returns `None` for those, causing HA to invoke `async_get_media_image()` instead, which delegates to the paired `CombinedCoverImage` image entity.

`media_image_remotely_accessible` returns `True` only when the source has both a direct CDN URL AND the source itself reports `media_image_remotely_accessible: True`.

### Extra State Attributes (Diagnostics)

```python
{
    "active_source": "media_player.spotify",        # always present
    "sources": ["media_player.spotify", "..."],     # always present
    "active_audio_source": "media_player.homepod",  # only if audio_sources configured
    "audio_sources": ["media_player.homepod"],      # only if audio_sources configured
}
```

---

## 6. Service Forwarding

### Routing

All service calls go through `_call_active(service, **kwargs)`:

```python
async def _call_active(self, service, **kwargs):
    target = self._active_audio_entity_id() or self._active_entity_id()
    if target is None:
        return  # silently no-op when no source is active
    await hass.services.async_call(
        "media_player", service,
        {"entity_id": target, **kwargs},
        blocking=True,
    )
```

**Routing priority**: audio source (if active) → display source → no-op.

### Forwarded Services

| Entity Method | HA Service Called | Extra kwargs |
|---|---|---|
| `async_media_play()` | `media_play` | — |
| `async_media_pause()` | `media_pause` | — |
| `async_media_stop()` | `media_stop` | — |
| `async_media_next_track()` | `media_next_track` | — |
| `async_media_previous_track()` | `media_previous_track` | — |
| `async_set_volume_level(volume)` | `volume_set` | `volume_level=volume` |
| `async_volume_up()` | `volume_up` | — |
| `async_volume_down()` | `volume_down` | — |
| `async_mute_volume(mute)` | `volume_mute` | `is_volume_muted=mute` |
| `async_media_seek(position)` | `media_seek` | `seek_position=position` |
| `async_play_media(type, id, **kw)` | `play_media` | `media_content_type`, `media_content_id`, `**kwargs` |
| `async_select_source(source)` | `select_source` | `source=source` |
| `async_set_shuffle(shuffle)` | `shuffle_set` | `shuffle=shuffle` |
| `async_set_repeat(repeat)` | `repeat_set` | `repeat=repeat` |
| `async_turn_on()` | `turn_on` | — |
| `async_turn_off()` | `turn_off` | — |
| `async_toggle()` | `toggle` | — |

All calls use `blocking=True` — the combined entity waits for the underlying service call to complete.

### Media Browsing (Special Case)

`async_browse_media()` does NOT use `_call_active()`. Instead it calls `_browse_entity_id()` which picks a delegate via this cascade:

1. Active display source, if it supports `BROWSE_MEDIA`
2. Active audio source, if it supports `BROWSE_MEDIA`
3. Any configured source (display or audio, regardless of state) that supports `BROWSE_MEDIA`

It then directly calls `entity.async_browse_media()` on the target entity object (not via `hass.services`), accessed through `hass.data["media_player"].get_entity()`.

---

## 7. Update Mechanism

### Event-Driven State Tracking (No Polling)

```python
_attr_should_poll = False

async def async_added_to_hass(self):
    all_tracked = list(dict.fromkeys(self._sources + self._audio_sources))
    self._unsub = async_track_state_change_event(
        self.hass, all_tracked, self._handle_state_change
    )

@callback
def _handle_state_change(self, event):
    self.async_write_ha_state()   # triggers HA to re-read all properties
```

When **any** tracked source entity changes state, the combined entity calls `async_write_ha_state()`. This causes HA to re-evaluate all `@property` methods (`state`, `media_title`, `volume_level`, etc.), which in turn call `_active_state()` / `_control_state()` to resolve the current winner. There is no intermediate caching — every property read goes through the full resolution logic.

### Lifecycle

- **Setup**: `async_added_to_hass()` registers listeners and refreshes source lists from the entry
- **Teardown**: `async_will_remove_from_hass()` calls `self._unsub()` to remove event listeners
- **Reconfigure**: Options flow save → `_async_update_listener` → `async_reload(entry_id)` → full teardown + fresh setup with new config

### Image Entity Update

The `CombinedCoverImage` entity also uses `async_track_state_change_event` on all display sources. On state change:

```python
@callback
def _handle_state_change(self, _event):
    self._refresh_image_url()      # bumps image_last_updated if fingerprint changed
    self.async_write_ha_state()
```

`_refresh_image_url()` compares a fingerprint string (`"{entity_id}:{entity_picture}"`) against the cached value. If it changed, it updates `_attr_image_last_updated` to `utcnow()`, which tells HA's image proxy that the content has changed and clients should re-fetch.

---

## 8. Image Entity & Cover Art Cache (image.py)

### CombinedCoverImage Entity

- Platform: `image`
- Unique ID: `{entry.unique_id}_cover`
- Shares device with the media player entity
- Uses same tier-based priority logic (imports `_TIER1`, `_TIER2`, `_TIER3`, `_safe_state` from `media_player.py`)

### Image Fetch Strategy (`async_image()`)

For each source in priority order (tier-first, then index):

1. **Cache check** — `_image_cache_key()` returns the most stable key, then checks memory → disk
2. **Entity delegation** — `entity.async_get_media_image()` on the source entity object
3. **URL fallback** — HTTP fetch from `entity_picture` attribute (resolves HA-relative paths to absolute URLs)
4. **Last-known-good** — If no source has an image, returns `self._last_image` (prevents blank cover during track transitions)

### Cache Key Strategy

```python
def _image_cache_key(state, entity_id):
    # Prefer stable CDN URL (survives HA restarts)
    url = state.attributes.get("media_image_url")
    if url.startswith("http"):
        return url
    # Fall back to session-scoped key (memory-only caching)
    ep = state.attributes.get("entity_picture")
    if ep:
        return f"{entity_id}:{ep}"
    return None
```

### Two-Layer Cache (`_CoverCache`)

| Layer | Storage | Key types | TTL | Survives restart |
|---|---|---|---|---|
| Memory | `dict[str, _MemEntry]` | All keys | 14 days (`time.monotonic()`) | No |
| Disk | `.storage/combined_media_player_cover_cache/` | Stable HTTP(S) URLs only | 14 days (`time.time()`) | Yes |

- **Disk index**: `index.json` maps `SHA256(url)[:32]` → `{content_type, last_used}`
- **Image files**: `{hash}.bin`
- **Daily cleanup**: `async_track_time_interval` prunes expired entries every 24 hours
- **Shutdown flush**: Index written to disk on `EVENT_HOMEASSISTANT_STOP`
- **Shared**: Stored in `hass.data[DOMAIN]["cover_cache"]`, initialized by the first `CombinedCoverImage` entity, reused by all others

---

## 9. Key Design Decisions for Porting

1. **No coordinator** — All state is derived on-demand from `hass.states.get()`. There is no stored/cached representation of the combined state. Each property access resolves fresh.

2. **Event-driven only** — `async_track_state_change_event` + `async_write_ha_state()` is the entire update loop. Zero polling.

3. **Display vs. control separation** — The `audio_sources` concept is not just about routing commands; it also changes which entity's attributes are read for volume/shuffle/repeat/features.

4. **Service calls, not direct entity method calls** — Commands are forwarded via `hass.services.async_call("media_player", service, ...)`, not by calling methods directly on entity objects. The exception is `async_browse_media` and `async_get_media_image`, which call entity methods directly via `hass.data["media_player"].get_entity()`.

5. **Always-available pattern** — The combined entity never becomes unavailable. It degrades gracefully to `OFF`.

6. **Stateless properties** — No intermediate state variables. Every `@property` calls through to `_active_state()` or `_control_state()` which scan the source list each time. This is simple but means N property reads = N scans of the source list per state write.

7. **Image caching is a separate entity** — Cover art logic lives entirely in `image.py`, not in the media player entity. The media player delegates to it via entity registry lookup + `async_image()`.
