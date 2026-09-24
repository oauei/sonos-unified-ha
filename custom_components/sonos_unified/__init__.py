"""The Sonos Unified integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
import voluptuous as vol

from .const import (
    CONF_DELAY_MS,
    DEFAULT_DELAY_MS,
    DOMAIN,
    EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED,
    SERVICE_SET_DELAY_OFFSET,
    SERVICE_START_CALIBRATION,
    SERVICE_TEST_SYNC,
)
from .stream_proxy import async_register_http_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

SET_DELAY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DELAY_MS): vol.Coerce(int),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Sonos Unified component."""
    # Register calibration HTTP views and endpoints
    async_register_http_views(hass)

    async def handle_set_delay_offset(call: ServiceCall) -> None:
        """Service to set delay offset directly."""
        delay_ms = call.data[CONF_DELAY_MS]
        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            new_options = dict(entry.options)
            new_options[CONF_DELAY_MS] = delay_ms
            hass.config_entries.async_update_entry(entry, options=new_options)
            hass.bus.async_fire(
                EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED,
                {"entry_id": entry.entry_id, "delay_ms": delay_ms},
            )
        _LOGGER.info("Updated Sonos Unified delay offset to %d ms", delay_ms)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DELAY_OFFSET,
        handle_set_delay_offset,
        schema=SET_DELAY_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sonos Unified from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
