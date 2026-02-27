# Combined Media Player

![Combined Media Player](custom_components/combined_media_player/icons/logo.png)

A Home Assistant custom integration that merges multiple media players into a single combined player with configurable priority logic.

## Features

- **Multiple sources** – any number of `media_player` entities as input sources
- **Priority order** – position 1 = highest priority, position N = lowest
- **Smart activity detection** – playing sources beat paused, paused beat on
- **Full media attributes** – title, artist, album, app name, series/season/episode, position, shuffle, repeat and more are proxied from the active source
- **Cover art image entity** – dedicated `image` entity for use in dashboards and automations
- **Transparent cover art** – forwards the active source's image (works with native cover as well as [Media Cover Art](https://github.com/Levtos/test_art))
- **Full control** – all commands (Play, Pause, Volume, Next, Seek, …) are forwarded to the active source
- **Clean state model** – only `playing`, `idle`, `on`, `off` – no `unavailable` or `unknown`
- **Device grouping** – media player and image entity are grouped under a single device in HA
- **UI-only setup** – no YAML required, fully configured via the UI

## Priority Logic

| Tier | States | Description |
|------|--------|-------------|
| 1 | `playing`, `buffering` | Actively playing |
| 2 | `paused`, `idle` | Paused / ready |
| 3 | `on` | Powered on but inactive |
| — | `off`, `unavailable`, `unknown` | Ignored |

Within the same tier, the source with the lower position (higher priority) wins.

**State mapping of the combined player:**

| Active source | Combined player |
|---------------|-----------------|
| `playing` / `buffering` | `playing` |
| `paused` / `idle` | `idle` |
| `on` | `on` |
| No active source | `off` |

## Entities

Each integration entry creates two entities under a shared device:

| Entity | Description |
|--------|-------------|
| `media_player.<name>` | Combined media player with full controls |
| `image.<name>_cover` | Cover art image of the currently active source |

The `image` entity is useful in dashboards (Picture card) and automations where a proper `image` entity is required instead of `entity_picture`.

Both entities expose an `active_source` attribute with the `entity_id` of the currently winning source.

## Installation

### HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom Repositories
2. URL: `https://github.com/Levtos/combined_mediaplayers`, Category: Integration
3. Install "Combined Media Player" and restart HA

### Manual

Copy the `custom_components/combined_media_player` folder into your `config/custom_components/` directory and restart HA.

## Configuration

1. **Settings → Devices & Services → Add Integration → Combined Media Player**
2. Enter a name (e.g. "Living Room")
3. Select source players – **the selection order determines the priority**
4. Done – `media_player.<name>` and `image.<name>_cover` appear immediately

Sources, their order and the name can be changed at any time under **Options** of the integration.

## Example: PS5 · Apple TV · HomePods

```
Prio 1: media_player.ps5             → Gaming    → native thumbnails
Prio 2: media_player.appletv         → Streaming → native cover art
Prio 3: media_player.homepods_cover  → Music     → iTunes cover via media_cover_art
```

The combined player automatically shows the image of the currently active source.
