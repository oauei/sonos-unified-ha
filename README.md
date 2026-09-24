# Sonos Unified

Unify Sonos **S1 (legacy)** and **S2 (modern)** speakers into a single, synchronized Home Assistant media player — with millisecond acoustic calibration via your phone's microphone.

## Features

- 🎵 **Single unified media player entity** across S1 + S2 generations
- ⏱️ **Millisecond-precise delay compensation** to eliminate echo between generations
- 📱 **Acoustic auto-calibration** using your phone's microphone (no extra hardware)
- 🎚️ **Manual fine-tuning slider** in the calibration UI and HA Options flow
- 🔊 **Proportional group volume** — adjusting master volume scales all speakers in ratio
- 🔗 **Standard HA grouping** — `media_player.join` / `unjoin` work as normal
- 📺 **Media browser delegation** — browse your Sonos music library through the unified entity
- ✅ **Does not touch the core Sonos integration** — fully forward-compatible

---

## Installation via HACS

1. Open HACS in your Home Assistant.
2. Go to **Integrations** → click the ⋮ menu → **Custom repositories**.
3. Add this repository URL and set category to **Integration**.
4. Click **Download** on the **Sonos Unified** card.
5. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Sonos Unified**.
3. Select your **Primary Coordinator** speaker (typically your S2 / newer speaker).
4. Select your **Secondary** speakers (your S1 / legacy speakers).
5. Leave delay at `0 ms` — calibrate it next.

## Acoustic Calibration

Open this URL on your phone while standing between your speakers:

```
http://<homeassistant-ip>:8123/api/sonos_unified/calibrate
```

Or embed it as a Lovelace Webpage card:

```yaml
type: iframe
url: /api/sonos_unified/calibrate
aspect_ratio: 75%
```

The page plays two reference chimes separated by exactly 2 seconds, records them via your microphone, and calculates the millisecond arrival difference using cross-correlation. Tap **Save** to apply.

## Manual Calibration

Three options:
- **Drag the slider** in the calibration page + hit **Play Metronome** to ear-test
- **Settings → Devices & Services → Sonos Unified → Configure** — adjust the delay slider
- **Developer Tools → Services** → call `sonos_unified.set_delay_offset` with `delay_ms: 145`

---

## How the Sync Works

```
delay_ms > 0  →  Secondary lags primary  →  Trigger secondary first, wait, then primary
delay_ms < 0  →  Secondary leads primary →  Trigger primary first, wait, then secondary
delay_ms = 0  →  Perfect lockstep        →  Trigger simultaneously
```
