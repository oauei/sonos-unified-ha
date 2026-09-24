# Sonos Unified (S1 & S2 Bridge)

A Home Assistant custom integration that unifies Sonos S1 (legacy) and S2 (modern) speakers into a single synchronized media player interface with **acoustic calibration** via your phone's microphone.

---

## The Problem
Sonos firmware intentionally isolates S1 and S2 devices into separate households and disables native UPnP/PTP cross-generation grouping. Playing audio across both systems results in a noticeable 100ms–400ms buffer latency offset (audible echo).

## The Solution
`sonos_unified` creates an aggregation layer on top of your existing Sonos entities without modifying the core Sonos integration:
1. **Intra-generation Native Grouping**: Keeps speakers of the same generation (S2+S2, S1+S1) grouped using native Sonos hardware PTP synchronization.
2. **Cross-generation Latency Compensation**: Synchronizes transport across S1 and S2 coordinators with millisecond-precision lead/lag compensation.
3. **Automated Acoustic Phone Calibration**: Uses your phone's microphone and Web Audio API to calculate the exact millisecond arrival offset ($\Delta t$) using cross-correlation against acoustic test chimes.
4. **Preserved UI**: Fully compatible with Home Assistant's standard media player cards, Media Browser, `mini-media-player`, and community Sonos cards (`custom:sonos-card`) via standard `group_members` attributes and `media_player.join`/`unjoin` services.

---

## Installation

### Manual Installation
1. Copy the `custom_components/sonos_unified` directory into your Home Assistant configuration directory under `custom_components/`:
   ```bash
   cp -r custom_components/sonos_unified <path_to_ha_config>/custom_components/
   ```
2. Restart Home Assistant.
3. In Home Assistant, go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Sonos Unified**.

---

## Configuration

1. **Primary Coordinator Speaker**: Select your main speaker (typically your primary S2 speaker, e.g., `media_player.living_room`).
2. **Secondary Speakers**: Select your secondary speakers (e.g., your S1 speakers, e.g., `media_player.kitchen_s1`).
3. **Delay Compensation (ms)**: Initial offset (default is `0 ms`). Can be calibrated automatically.

---

## Acoustic Phone Calibration

1. On your phone (connected to the same local Wi-Fi or via your Home Assistant app/browser), navigate to:
   ```
   http://<homeassistant-ip>:8123/api/sonos_unified/calibrate
   ```
   *(Or open it in a Lovelace Webpage / Iframe card)*.
2. Stand roughly between your S2 and S1 listening areas with your phone.
3. Tap **Start Acoustic Calibration** and allow microphone access.
4. Two reference chimes will play (Speaker A, then Speaker B after 2 seconds).
5. The tool analyzes the acoustic arrival times using real-time cross-correlation and calculates the delay:
   $$\Delta t = t_{\text{Secondary}} - t_{\text{Primary}} - 2000\,\text{ms}$$
6. Tap **Save to Home Assistant** to immediately store the calibrated offset.
7. Tap **Play Metronome Click Test** to confirm that the speakers sound like a single, synchronized tick without echo.

---

## Dashboard Card Example

You can use the standard Home Assistant Media Control card or `mini-media-player`:

```yaml
type: custom:mini-media-player
entity: media_player.sonos_unified_group
group: true
speaker_group:
  platform: sonos
  show_group_count: true
  entities:
    - entity_id: media_player.living_room
      name: Living Room (S2)
    - entity_id: media_player.kitchen
      name: Kitchen (S1)
```

---

## Services

### `sonos_unified.set_delay_offset`
Adjust delay compensation dynamically:
```yaml
service: sonos_unified.set_delay_offset
data:
  delay_ms: 145
```
