"""Config flow for Sonos Unified integration."""

from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.media_player import DOMAIN as MP_DOMAIN
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DELAY_MS,
    CONF_NAME,
    CONF_PRIMARY_SPEAKER,
    CONF_SECONDARY_SPEAKERS,
    DEFAULT_DELAY_MS,
    DEFAULT_NAME,
    DOMAIN,
)


def _get_sonos_media_players(hass) -> list[str]:
    """Retrieve all available media player entity IDs in Home Assistant."""
    players = []
    for state in hass.states.async_all(MP_DOMAIN):
        players.append(state.entity_id)
    return sorted(players)


class SonosUnifiedConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sonos Unified."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}
        available_players = _get_sonos_media_players(self.hass)

        if user_input is not None:
            primary = user_input[CONF_PRIMARY_SPEAKER]
            secondaries = user_input.get(CONF_SECONDARY_SPEAKERS, [])

            if primary in secondaries:
                errors["base"] = "primary_in_secondary"
            else:
                await self.async_set_unique_id(f"sonos_unified_{primary}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_PRIMARY_SPEAKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=MP_DOMAIN)
                ),
                vol.Required(CONF_SECONDARY_SPEAKERS): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=MP_DOMAIN, multiple=True)
                ),
                vol.Optional(CONF_DELAY_MS, default=DEFAULT_DELAY_MS): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-1000,
                        max=1000,
                        step=1,
                        unit_of_measurement="ms",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SonosUnifiedOptionsFlowHandler(config_entry)


class SonosUnifiedOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Sonos Unified."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_delay = self.config_entry.options.get(
            CONF_DELAY_MS,
            self.config_entry.data.get(CONF_DELAY_MS, DEFAULT_DELAY_MS),
        )
        current_secondaries = self.config_entry.options.get(
            CONF_SECONDARY_SPEAKERS,
            self.config_entry.data.get(CONF_SECONDARY_SPEAKERS, []),
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DELAY_MS, default=current_delay
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-1000,
                        max=1000,
                        step=1,
                        unit_of_measurement="ms",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(
                    CONF_SECONDARY_SPEAKERS, default=current_secondaries
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=MP_DOMAIN, multiple=True)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
