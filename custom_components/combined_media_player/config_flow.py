from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
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
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "CombinedMediaPlayerOptionsFlow":
        return CombinedMediaPlayerOptionsFlow()


class CombinedMediaPlayerOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            new_name = user_input.get(CONF_NAME, "").strip()
            if not new_name:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(user_input),
                    errors={CONF_NAME: "name_required"},
                )
            if new_name != self.config_entry.title:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=new_name
                )
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_schema(),
        )

    def _build_schema(self, prefill: dict | None = None) -> vol.Schema:
        current_name = (
            prefill.get(CONF_NAME)
            if prefill
            else (
                self.config_entry.options.get(CONF_NAME)
                or self.config_entry.data.get(CONF_NAME, "")
            )
        )
        current_sources = (
            prefill.get(CONF_SOURCES)
            if prefill
            else list(
                self.config_entry.options.get(CONF_SOURCES)
                or self.config_entry.data.get(CONF_SOURCES, [])
            )
        )
        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=current_name): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(CONF_SOURCES, default=current_sources): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="media_player",
                        multiple=True,
                    )
                ),
            }
        )
