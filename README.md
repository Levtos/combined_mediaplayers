# Combined Media Player

![Combined Media Player](custom_components/combined_media_player/icon.png)

A Home Assistant custom integration that merges multiple media players into a single combined player with configurable priority logic.

## Features

- **Multiple sources** – any number of `media_player` entities as input sources
- **Priority order** – position 1 = highest priority, position N = lowest
- **Smart activity detection** – playing sources beat paused, paused beat on
- **Transparent cover art** – forwards the active source's image (works with native cover as well as [Media Cover Art](https://github.com/Levtos/test_art))
- **Full control** – all commands (Play, Pause, Volume, Next, …) are forwarded to the active source
- **Clean state model** – only `playing`, `idle`, `on`, `off` – no `unavailable` or `unknown`

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
4. Done – the entity `media_player.<name>` appears immediately

Sources and their order can be changed at any time under **Options** of the integration.

## Example: PS5 · Apple TV · HomePods

```
Prio 1: media_player.ps5             → Gaming    → native thumbnails
Prio 2: media_player.appletv         → Streaming → native cover art
Prio 3: media_player.homepods_cover  → Music     → iTunes cover via media_cover_art
```

The combined player automatically shows the image of the currently active source.
