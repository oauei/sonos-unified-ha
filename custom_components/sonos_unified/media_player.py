"""Unified Media Player entity for bridging Sonos S1 and S2 speakers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    DOMAIN as MP_DOMAIN,
    SERVICE_PLAY_MEDIA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_SEEK,
    SERVICE_MEDIA_STOP,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_DELAY_MS,
    CONF_NAME,
    CONF_PRIMARY_SPEAKER,
    CONF_SECONDARY_SPEAKERS,
    DEFAULT_DELAY_MS,
    DEFAULT_NAME,
    DOMAIN,
    EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Sonos Unified media player entity from a config entry."""
    entity = SonosUnifiedMediaPlayer(hass, entry)
    async_add_entities([entity], True)


class SonosUnifiedMediaPlayer(MediaPlayerEntity):
    """Unified Media Player controlling S1 and S2 Sonos systems in lockstep."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the unified player."""
        self.hass = hass
        self.entry = entry
        self._attr_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}"

        self.primary_entity: str = entry.data[CONF_PRIMARY_SPEAKER]
        self.secondary_entities: list[str] = list(entry.data.get(CONF_SECONDARY_SPEAKERS, []))
        self.active_group: list[str] = [self.primary_entity] + self.secondary_entities

        # Delay compensation: positive = secondary lags primary; negative = secondary leads
        self.delay_ms: int = entry.options.get(
            CONF_DELAY_MS, entry.data.get(CONF_DELAY_MS, DEFAULT_DELAY_MS)
        )

        self._attr_supported_features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.SEEK
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.GROUPING
        )

        self._unsub_listeners: list[Any] = []

    async def async_added_to_hass(self) -> None:
        """Subscribe to member speaker state updates and calibration events."""
        all_monitored = list(set([self.primary_entity] + self.secondary_entities))

        @callback
        def _async_on_speaker_state_change(event: Event) -> None:
            self._update_from_members()
            self.async_write_ha_state()

        self._unsub_listeners.append(
            async_track_state_change_event(
                self.hass, all_monitored, _async_on_speaker_state_change
            )
        )

        @callback
        def _async_on_calibration_updated(event: Event) -> None:
            if event.data.get("entry_id") == self.entry.entry_id:
                self.delay_ms = int(event.data.get("delay_ms", 0))
                self.async_write_ha_state()

        self._unsub_listeners.append(
            self.hass.bus.async_listen(
                EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED, _async_on_calibration_updated
            )
        )

        self._update_from_members()

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    @callback
    def _update_from_members(self) -> None:
        """Mirror playback state and metadata from the primary speaker."""
        primary_state = self.hass.states.get(self.primary_entity)
        if not primary_state:
            self._attr_state = MediaPlayerState.OFF
            return

        # State mapping
        state_str = primary_state.state
        if state_str == STATE_PLAYING:
            self._attr_state = MediaPlayerState.PLAYING
        elif state_str == STATE_PAUSED:
            self._attr_state = MediaPlayerState.PAUSED
        elif state_str in (STATE_IDLE, STATE_ON):
            self._attr_state = MediaPlayerState.IDLE
        elif state_str == STATE_OFF:
            self._attr_state = MediaPlayerState.OFF
        else:
            self._attr_state = MediaPlayerState.IDLE

        attrs = primary_state.attributes
        self._attr_media_title = attrs.get("media_title")
        self._attr_media_artist = attrs.get("media_artist")
        self._attr_media_album_name = attrs.get("media_album_name")
        self._attr_media_image_url = attrs.get("entity_picture")
        self._attr_media_duration = attrs.get("media_duration")
        self._attr_media_position = attrs.get("media_position")
        self._attr_media_position_updated_at = attrs.get("media_position_updated_at")
        self._attr_source = attrs.get("source")
        self._attr_source_list = attrs.get("source_list")

        # Compute average volume across active group members
        volumes = []
        is_muted_list = []
        for entity_id in self.active_group:
            st = self.hass.states.get(entity_id)
            if st and st.attributes.get("volume_level") is not None:
                volumes.append(st.attributes["volume_level"])
            if st and st.attributes.get("is_volume_muted") is not None:
                is_muted_list.append(st.attributes["is_volume_muted"])

        if volumes:
            self._attr_volume_level = sum(volumes) / len(volumes)
        else:
            self._attr_volume_level = attrs.get("volume_level", 0.5)

        self._attr_is_volume_muted = any(is_muted_list) if is_muted_list else False

        # Expose standard group_members so standard Lovelace cards show grouping UI
        self._attr_group_members = list(self.active_group)

        self._attr_extra_state_attributes = {
            "primary_speaker": self.primary_entity,
            "secondary_speakers": self.secondary_entities,
            "active_group": self.active_group,
            "delay_offset_ms": self.delay_ms,
            "calibration_page": "/api/sonos_unified/calibrate",
        }

    #
    # Playback Controls with Latency-Compensated Dispatch
    #
    async def _async_call_speaker_service(
        self,
        service: str,
        entity_id: str,
        service_data: dict[str, Any] | None = None,
    ) -> None:
        """Dispatch a service call to an underlying media player."""
        data = {ATTR_ENTITY_ID: entity_id}
        if service_data:
            data.update(service_data)
        await self.hass.services.async_call(MP_DOMAIN, service, data, blocking=False)

    async def async_media_play(self) -> None:
        """Send play command with calibrated delay compensation."""
        delay_sec = abs(self.delay_ms) / 1000.0

        if self.delay_ms >= 0:
            # Secondary lags: trigger secondary first to allow its longer buffer to fill
            for sec in self.secondary_entities:
                if sec in self.active_group:
                    await self._async_call_speaker_service(SERVICE_MEDIA_PLAY, sec)
            if delay_sec > 0.005:
                await asyncio.sleep(delay_sec)
            await self._async_call_speaker_service(SERVICE_MEDIA_PLAY, self.primary_entity)
        else:
            # Secondary leads: trigger primary first
            await self._async_call_speaker_service(SERVICE_MEDIA_PLAY, self.primary_entity)
            if delay_sec > 0.005:
                await asyncio.sleep(delay_sec)
            for sec in self.secondary_entities:
                if sec in self.active_group:
                    await self._async_call_speaker_service(SERVICE_MEDIA_PLAY, sec)

    async def async_media_pause(self) -> None:
        """Pause all active group speakers simultaneously."""
        tasks = [
            self._async_call_speaker_service(SERVICE_MEDIA_PAUSE, entity_id)
            for entity_id in self.active_group
        ]
        await asyncio.gather(*tasks)

    async def async_media_stop(self) -> None:
        """Stop all active group speakers."""
        tasks = [
            self._async_call_speaker_service(SERVICE_MEDIA_STOP, entity_id)
            for entity_id in self.active_group
        ]
        await asyncio.gather(*tasks)

    async def async_media_next_track(self) -> None:
        """Next track on primary coordinator."""
        await self._async_call_speaker_service(SERVICE_MEDIA_NEXT_TRACK, self.primary_entity)

    async def async_media_previous_track(self) -> None:
        """Previous track on primary coordinator."""
        await self._async_call_speaker_service(SERVICE_MEDIA_PREVIOUS_TRACK, self.primary_entity)

    async def async_media_seek(self, position: float) -> None:
        """Seek on primary coordinator."""
        await self._async_call_speaker_service(
            SERVICE_MEDIA_SEEK, self.primary_entity, {"seek_position": position}
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Send play_media to all active group members with delay compensation."""
        service_data = {
            ATTR_MEDIA_CONTENT_TYPE: media_type,
            ATTR_MEDIA_CONTENT_ID: media_id,
        }
        if "extra" in kwargs:
            service_data["extra"] = kwargs["extra"]
        if "announce" in kwargs:
            service_data["announce"] = kwargs["announce"]

        delay_sec = abs(self.delay_ms) / 1000.0

        if self.delay_ms >= 0:
            # Secondary lags: trigger secondary buffer first
            for sec in self.secondary_entities:
                if sec in self.active_group:
                    await self._async_call_speaker_service(
                        SERVICE_PLAY_MEDIA, sec, service_data
                    )
            if delay_sec > 0.005:
                await asyncio.sleep(delay_sec)
            await self._async_call_speaker_service(
                SERVICE_PLAY_MEDIA, self.primary_entity, service_data
            )
        else:
            # Secondary leads: trigger primary buffer first
            await self._async_call_speaker_service(
                SERVICE_PLAY_MEDIA, self.primary_entity, service_data
            )
            if delay_sec > 0.005:
                await asyncio.sleep(delay_sec)
            for sec in self.secondary_entities:
                if sec in self.active_group:
                    await self._async_call_speaker_service(
                        SERVICE_PLAY_MEDIA, sec, service_data
                    )

    #
    # Volume Management Across Members
    #
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume proportionally across all active group members."""
        current_master = self._attr_volume_level or 0.5
        ratio = (volume / current_master) if current_master > 0 else 1.0

        tasks = []
        for entity_id in self.active_group:
            st = self.hass.states.get(entity_id)
            if st and st.attributes.get("volume_level") is not None:
                new_vol = min(1.0, max(0.0, st.attributes["volume_level"] * ratio))
            else:
                new_vol = volume
            tasks.append(
                self._async_call_speaker_service(
                    SERVICE_VOLUME_SET, entity_id, {"volume_level": new_vol}
                )
            )
        await asyncio.gather(*tasks)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute/unmute all active group members."""
        tasks = [
            self._async_call_speaker_service(
                SERVICE_VOLUME_MUTE, entity_id, {"is_volume_muted": mute}
            )
            for entity_id in self.active_group
        ]
        await asyncio.gather(*tasks)

    #
    # Standard Grouping / Joining API (Preserving Sonos UI & Mini-Media-Player)
    #
    async def async_join_players(self, group_members: list[str]) -> None:
        """Add speakers to this unified group."""
        _LOGGER.info("Joining speakers to Sonos Unified group: %s", group_members)
        for member in group_members:
            if member not in self.active_group:
                self.active_group.append(member)

        # Synchronize newly joined players with current playing media if active
        if self._attr_state == MediaPlayerState.PLAYING and self._attr_media_title:
            st = self.hass.states.get(self.primary_entity)
            if st and st.attributes.get("media_content_id"):
                for member in group_members:
                    await self._async_call_speaker_service(
                        SERVICE_PLAY_MEDIA,
                        member,
                        {
                            ATTR_MEDIA_CONTENT_ID: st.attributes["media_content_id"],
                            ATTR_MEDIA_CONTENT_TYPE: st.attributes.get(
                                "media_content_type", MediaType.MUSIC
                            ),
                        },
                    )

        self._update_from_members()
        self.async_write_ha_state()

    async def async_unjoin_player(self) -> None:
        """Unjoin secondary speakers, reverting to primary speaker only."""
        _LOGGER.info("Unjoining secondary speakers from Sonos Unified group")
        for member in list(self.active_group):
            if member != self.primary_entity:
                await self._async_call_speaker_service(SERVICE_MEDIA_STOP, member)

        self.active_group = [self.primary_entity]
        self._update_from_members()
        self.async_write_ha_state()

    #
    # Media Browser Delegation
    #
    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> Any:
        """Browse media by delegating directly to the primary Sonos speaker or media_source."""
        try:
            component = self.hass.data.get(MP_DOMAIN)
            if component and hasattr(component, "get_entity"):
                primary_entity_component = component.get_entity(self.primary_entity)
                if primary_entity_component and hasattr(
                    primary_entity_component, "async_browse_media"
                ):
                    return await primary_entity_component.async_browse_media(
                        media_content_type, media_content_id
                    )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "Could not delegate browse_media directly to %s: %s",
                self.primary_entity,
                exc,
            )

        if "media_source" in self.hass.config.components:
            from homeassistant.components import media_source

            return await media_source.async_browse_media(
                self.hass, media_content_id, content_filter=lambda item: True
            )
        return None

