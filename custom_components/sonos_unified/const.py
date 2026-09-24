"""Constants for the Sonos Unified integration."""

DOMAIN = "sonos_unified"

# Configuration keys
CONF_PRIMARY_SPEAKER = "primary_speaker"
CONF_SECONDARY_SPEAKERS = "secondary_speakers"
CONF_ALL_SPEAKERS = "speakers"
CONF_DELAY_MS = "delay_ms"
CONF_BUFFER_MS = "buffer_ms"
CONF_NAME = "name"
CONF_ENABLE_STREAM_PROXY = "enable_stream_proxy"

# Defaults
DEFAULT_NAME = "Sonos Unified Group"
DEFAULT_DELAY_MS = 0
DEFAULT_BUFFER_MS = 500
DEFAULT_CHIRP_INTERVAL_MS = 2000

# Service names
SERVICE_SET_DELAY_OFFSET = "set_delay_offset"
SERVICE_START_CALIBRATION = "start_calibration"
SERVICE_TEST_SYNC = "test_sync"
SERVICE_UNIFY_GROUP = "unify_group"

# API Endpoints
API_CHIRP_URL = "/api/sonos_unified/calibration/chirp.wav"
API_CLICK_URL = "/api/sonos_unified/calibration/click.wav"
API_CALIBRATE_PAGE = "/api/sonos_unified/calibrate"
API_CALIBRATE_RESULT = "/api/sonos_unified/calibration/result"
API_STREAM_PROXY = "/api/sonos_unified/stream"

# Signals and Events
EVENT_SONOS_UNIFIED_CALIBRATION_UPDATED = f"{DOMAIN}_calibration_updated"
SIGNAL_SONOS_UNIFIED_STATE_UPDATE = f"{DOMAIN}_state_update"
