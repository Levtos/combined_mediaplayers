from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import CONF_NAME, CONF_SOURCES, DOMAIN


class CombinedMediaPlayerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input.get(CONF_NAME, "").strip()
            sources = user_input.get(CONF_SOURCES) or []

            if not name:
                errors[CONF_NAME] = "name_required"
            elif not sources:
                errors[CONF_SOURCES] = "sources_required"
            else:
                await self.async_set_unique_id(
                    f"combined_{name.lower().replace(' ', '_')}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_SOURCES: list(sources),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_SOURCES): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="media_player",
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "CombinedMediaPlayerOptionsFlow":
        return CombinedMediaPlayerOptionsFlow(config_entry)


class CombinedMediaPlayerOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_sources = self.config_entry.options.get(
            CONF_SOURCES,
            self.config_entry.data.get(CONF_SOURCES, []),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCES, default=list(current_sources)): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="media_player",
                            multiple=True,
                        )
                    ),
                }
            ),
        )
