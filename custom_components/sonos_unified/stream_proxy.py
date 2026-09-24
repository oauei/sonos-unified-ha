"""HTTP views and audio proxy for Sonos Unified."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    DOMAIN as MP_DOMAIN,
    SERVICE_PLAY_MEDIA,
    MediaType,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import get_url

from .calibration import generate_calibration_wav, generate_metronome_wav
from .const import (
    API_CALIBRATE_PAGE,
    API_CALIBRATE_RESULT,
    API_CHIRP_URL,
    API_CLICK_URL,
    CONF_DELAY_MS,
    CONF_PRIMARY_SPEAKER,
    CONF_SECONDARY_SPEAKERS,
    DEFAULT_CHIRP_INTERVAL_MS,
    DOMAIN,
    EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


class CalibrationPageView(HomeAssistantView):
    """View to serve the acoustic calibration web page."""

    url = API_CALIBRATE_PAGE
    name = "api:sonos_unified:calibrate"
    requires_auth = False  # Allows loading in browser or lovelace iframe easily

    async def get(self, request: web.Request) -> web.Response:
        """Serve the calibration HTML page."""
        html_path = Path(__file__).parent / "frontend" / "calibration.html"
        try:
            content = await asyncio.to_thread(html_path.read_text, encoding="utf-8")
            return web.Response(text=content, content_type="text/html")
        except FileNotFoundError:
            return web.Response(status=404, text="Calibration page not found")


class CalibrationChirpAudioView(HomeAssistantView):
    """View to serve the reference chirp WAV."""

    url = API_CHIRP_URL
    name = "api:sonos_unified:calibration:chirp"
    requires_auth = False

    def __init__(self) -> None:
        """Cache the generated chirp in memory."""
        self._wav_data = generate_calibration_wav()

    async def get(self, request: web.Request) -> web.Response:
        """Return the WAV audio data."""
        return web.Response(
            body=self._wav_data,
            content_type="audio/wav",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(len(self._wav_data))},
        )


class CalibrationClickAudioView(HomeAssistantView):
    """View to serve the metronome click test WAV."""

    url = API_CLICK_URL
    name = "api:sonos_unified:calibration:click"
    requires_auth = False

    def __init__(self) -> None:
        """Cache the generated click track in memory."""
        self._wav_data = generate_metronome_wav()

    async def get(self, request: web.Request) -> web.Response:
        """Return the metronome WAV audio data."""
        return web.Response(
            body=self._wav_data,
            content_type="audio/wav",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(len(self._wav_data))},
        )


class CalibrationStartView(HomeAssistantView):
    """View to trigger calibration playback sequence across speakers."""

    url = "/api/sonos_unified/calibration/start"
    name = "api:sonos_unified:calibration:start"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Trigger calibration chirps with precise time interval."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return web.json_response({"error": "No Sonos Unified entry configured"}, status=400)

        entry = entries[0]
        data = entry.data
        primary_entity = data.get(CONF_PRIMARY_SPEAKER)
        secondary_entities = data.get(CONF_SECONDARY_SPEAKERS, [])

        if not primary_entity or not secondary_entities:
            return web.json_response(
                {"error": "Primary or secondary speaker not configured"}, status=400
            )

        secondary_entity = secondary_entities[0]
        base_url = get_url(self.hass, prefer_external=False)
        chirp_url = f"{base_url}{API_CHIRP_URL}"

        _LOGGER.info("Starting acoustic calibration playback on %s and %s", primary_entity, secondary_entity)

        # 1. Play chirp on Primary Speaker
        await self.hass.services.async_call(
            MP_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: primary_entity,
                ATTR_MEDIA_CONTENT_ID: chirp_url,
                ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
            },
            blocking=False,
        )

        # 2. Wait exactly DEFAULT_CHIRP_INTERVAL_MS (2000ms)
        await asyncio.sleep(DEFAULT_CHIRP_INTERVAL_MS / 1000.0)

        # 3. Play chirp on Secondary Speaker
        await self.hass.services.async_call(
            MP_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: secondary_entity,
                ATTR_MEDIA_CONTENT_ID: chirp_url,
                ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
            },
            blocking=False,
        )

        return web.json_response({"status": "success", "interval_ms": DEFAULT_CHIRP_INTERVAL_MS})


class CalibrationResultView(HomeAssistantView):
    """View to receive and save the measured delay offset."""

    url = API_CALIBRATE_RESULT
    name = "api:sonos_unified:calibration:result"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Save calibrated delay offset into config entry options."""
        payload = await request.json()
        delay_ms = payload.get("delay_ms")
        if delay_ms is None:
            return web.json_response({"error": "Missing delay_ms"}, status=400)

        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return web.json_response({"error": "No Sonos Unified entry found"}, status=404)

        entry = entries[0]
        new_options = dict(entry.options)
        new_options[CONF_DELAY_MS] = int(delay_ms)

        self.hass.config_entries.async_update_entry(entry, options=new_options)
        self.hass.bus.async_fire(
            EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED,
            {"entry_id": entry.entry_id, "delay_ms": delay_ms},
        )
        _LOGGER.info("Saved Sonos Unified delay offset: %s ms", delay_ms)
        return web.json_response({"status": "saved", "delay_ms": delay_ms})


class CalibrationCurrentView(HomeAssistantView):
    """View to retrieve current calibration delay offset."""

    url = "/api/sonos_unified/calibration/current"
    name = "api:sonos_unified:calibration:current"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Return current delay offset."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        delay_ms = 0
        if entries:
            entry = entries[0]
            delay_ms = entry.options.get(CONF_DELAY_MS, entry.data.get(CONF_DELAY_MS, 0))
        return web.json_response({"delay_ms": delay_ms})


class TestSyncView(HomeAssistantView):
    """View to play synchronized metronome clicks to test alignment."""

    url = "/api/sonos_unified/test_sync"
    name = "api:sonos_unified:test_sync"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Play synchronized metronome on all group speakers with delay compensation."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return web.json_response({"error": "No Sonos Unified entry found"}, status=400)

        entry = entries[0]
        data = entry.data
        options = entry.options
        primary_entity = data.get(CONF_PRIMARY_SPEAKER)
        secondary_entities = data.get(CONF_SECONDARY_SPEAKERS, [])
        delay_ms = options.get(CONF_DELAY_MS, data.get(CONF_DELAY_MS, 0))

        base_url = get_url(self.hass, prefer_external=False)
        click_url = f"{base_url}{API_CLICK_URL}"

        # If secondary lags (delay_ms > 0), start secondary earlier by delay_ms
        # If secondary leads (delay_ms < 0), start primary earlier by abs(delay_ms)
        delay_sec = abs(delay_ms) / 1000.0

        if delay_ms >= 0:
            # Secondary lags: trigger secondary first, wait delay_ms, then primary
            for sec_entity in secondary_entities:
                await self.hass.services.async_call(
                    MP_DOMAIN,
                    SERVICE_PLAY_MEDIA,
                    {
                        ATTR_ENTITY_ID: sec_entity,
                        ATTR_MEDIA_CONTENT_ID: click_url,
                        ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                    },
                    blocking=False,
                )
            if delay_sec > 0.001:
                await asyncio.sleep(delay_sec)
            await self.hass.services.async_call(
                MP_DOMAIN,
                SERVICE_PLAY_MEDIA,
                {
                    ATTR_ENTITY_ID: primary_entity,
                    ATTR_MEDIA_CONTENT_ID: click_url,
                    ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                },
                blocking=False,
            )
        else:
            # Secondary leads: trigger primary first, wait delay_ms, then secondary
            await self.hass.services.async_call(
                MP_DOMAIN,
                SERVICE_PLAY_MEDIA,
                {
                    ATTR_ENTITY_ID: primary_entity,
                    ATTR_MEDIA_CONTENT_ID: click_url,
                    ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                },
                blocking=False,
            )
            if delay_sec > 0.001:
                await asyncio.sleep(delay_sec)
            for sec_entity in secondary_entities:
                await self.hass.services.async_call(
                    MP_DOMAIN,
                    SERVICE_PLAY_MEDIA,
                    {
                        ATTR_ENTITY_ID: sec_entity,
                        ATTR_MEDIA_CONTENT_ID: click_url,
                        ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
                    },
                    blocking=False,
                )

        return web.json_response({"status": "playing", "delay_ms": delay_ms})


def async_register_http_views(hass: HomeAssistant) -> None:
    """Register all HTTP endpoints for calibration and audio serving."""
    hass.http.register_view(CalibrationPageView())
    hass.http.register_view(CalibrationChirpAudioView())
    hass.http.register_view(CalibrationClickAudioView())
    hass.http.register_view(CalibrationStartView(hass))
    hass.http.register_view(CalibrationResultView(hass))
    hass.http.register_view(CalibrationCurrentView(hass))
    hass.http.register_view(TestSyncView(hass))
