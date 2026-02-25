# Changelog

## 1.0.0 (2026-02-25)
- Initial release: Combined Media Player integration
- Config flow: create combined player via UI with name + source selection
- Priority logic: position 1 = highest priority, descending
- State tiers: playing/buffering > paused/idle > on; off/unavailable/unknown → ignored
- Removed deprecated `MediaPlayerState.STANDBY` (removed in HA Core 2026.8.0)
- Transparent cover art forwarded from active source (native or media_cover_art)
- All media player controls forwarded to the active source
- Options flow: edit sources and priority order at any time
- State model: only `playing`, `idle`, `on`, `off` – no `unavailable` or `unknown`
