from __future__ import annotations

import os

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SOURCES, DOMAIN, PLATFORMS

_PANEL_REGISTERED_KEY = f"{DOMAIN}_panel_registered"
_STATIC_URL_PATH = f"/{DOMAIN}_panel"
_PANEL_FRONTEND_URL = "combined-media-player-order"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register the reorder panel and WebSocket commands exactly once.
    if not hass.data.get(_PANEL_REGISTERED_KEY):
        hass.data[_PANEL_REGISTERED_KEY] = True

        www_dir = os.path.join(os.path.dirname(__file__), "www")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_STATIC_URL_PATH, www_dir, cache_headers=False)]
        )

        async_register_built_in_panel(
            hass,
            "custom",
            sidebar_title="Gerätereihenfolge",
            sidebar_icon="mdi:sort",
            frontend_url_path=_PANEL_FRONTEND_URL,
            config={
                "_panel_custom": {
                    "name": "combined-mp-order-panel",
                    "module_url": f"{_STATIC_URL_PATH}/panel.js",
                }
            },
            require_admin=True,
        )

        websocket_api.async_register_command(hass, ws_get_entries)
        websocket_api.async_register_command(hass, ws_reorder_sources)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ── WebSocket commands ────────────────────────────────────────────────────────


@websocket_api.websocket_command(
    {
        vol.Required("type"): "combined_media_player/get_entries",
    }
)
@websocket_api.async_response
async def ws_get_entries(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return all combined_media_player config entries with their source lists."""
    entries = []
    for entry_id, value in hass.data.get(DOMAIN, {}).items():
        if not isinstance(value, ConfigEntry):
            continue
        sources = list(
            value.options.get(CONF_SOURCES) or value.data.get(CONF_SOURCES, [])
        )
        entries.append(
            {
                "entry_id": value.entry_id,
                "title": value.title,
                "sources": sources,
            }
        )
    connection.send_result(msg["id"], {"entries": entries})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "combined_media_player/reorder_sources",
        vol.Required("entry_id"): str,
        vol.Required("sources"): [str],
    }
)
@websocket_api.async_response
async def ws_reorder_sources(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Persist a new source order for the given config entry."""
    entry_id: str = msg["entry_id"]
    sources: list[str] = msg["sources"]

    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return

    new_options = {**entry.options, CONF_SOURCES: sources}
    hass.config_entries.async_update_entry(entry, options=new_options)
    connection.send_result(msg["id"], {"success": True})
