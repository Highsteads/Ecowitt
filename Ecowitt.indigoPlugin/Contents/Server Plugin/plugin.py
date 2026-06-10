#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Ecowitt Weather Station plugin for Indigo
#              Receives push data via Ecowitt custom HTTP server upload protocol.
#              Compatible with Ecowitt, Fine Offset, Ambient Weather, Froggit,
#              Aercus Instruments, Bresser and other brands using the same protocol.
#              Tested with: Ecowitt HP2561 (7-in-1 Wi-Fi Solar Weather Station)
# Author:      CliveS & Claude Opus 4.7
# Date:        10-06-2026
# Version:     2.2.5
#
# v2.2.2 (23-05-2026): Added plugin_utils.install_timestamp_filter() wiring so
# self.logger.* calls also get the [HH:MM:SS.mmm] prefix (previously only the
# module-level log() helper honoured the toggle). The existing
# "Toggle Timestamp Logging" menu now flips BOTH the global flag and the new
# filter in sync. Matches Device Activity Monitor convention.
#
# v2.2.1 (22-05-2026):
# - PASSKEY now loads from IndigoSecrets.ECOWITT_PASSKEY first, with the
#   PluginConfig `expectedPasskey` field as fallback.  Keeps the gateway
#   identifier out of the plugin database (one master file, shared across
#   plugins) per the standard secrets policy.
#
# v2.2.0 (22-05-2026):
# - New Main Gateway states `connectionStatus` (Live / Stale / Offline) and
#   `lastUpdateAgeSec` — give a queryable, trigger-friendly view of gateway
#   health rather than relying on the boolean deviceOnline alone.  The Main
#   device's UiDisplayStateId now shows connectionStatus.
# - Optional PASSKEY routing: set `expectedPasskey` in Plugin Preferences to
#   accept pushes from only that gateway.  Useful if another Ecowitt device on
#   the LAN starts uploading to this server unexpectedly.  Blank = accept any.
# - Stale-check (still runs every 60 s) now also writes connectionStatus =
#   "Stale" / "Live" on every tick, so the Main device always reflects the
#   current freshness of the feed.
# - Info.plist ServerApiVersion bumped 3.0 -> 3.4 to align with Indigo 2025.2.
#
# v2.1.1 (13-05-2026):
# - Bundle plugin_utils.py inside the plugin (was missing — banner was falling
#   back to a one-liner because the import was looking in the wrong directory).
# - Fix sys.path.insert: use os.getcwd() (the plugin's own Server Plugin/ folder)
#   instead of the shared IndigoSecrets directory. This plugin uses no secrets
#   so only the bundle-local path is needed.
# - Add showPluginInfo menu item + callback that re-runs the startup banner
#   (per global CLAUDE.md standard pattern).
# - showPluginStatus: drop hardcoded "2.0.0" string, use self.pluginVersion.
#
# v2.1.0 (10-05-2026):
# - CRITICAL fix: rename custom state `batteryLevel` -> `battery` (Integer).
#   `batteryLevel` collided with Indigo's reserved native device property and
#   silently routed every battery write to the wrong slot, so the Custom
#   States panel never showed a battery percentage and the device list showed
#   0% / 1% (raw 0/1 binary flags from wh65batt etc).
# - New helper `battery_to_percent` correctly maps Ecowitt's two battery
#   encodings to a 0-100 integer:
#     * binary flag (0 = OK, 1 = Low) -> 100% / 0%
#     * voltage (e.g. 1.5V) -> linear interpolation between 1.2V and 1.6V
#   `is_low` and the Pushover low-battery alert are now driven by the
#   normalised percentage, not the raw payload value (the previous threshold
#   comparison treated voltage 1.5V as "below 20%" and triggered constant
#   low-battery alerts on healthy soil/leak/PM2.5 sensors).
# - Capture all Ecowitt payload fields as dynamic states on the Main Gateway
#   device.  Anything sent by the gateway that isn't already mapped to a
#   typed sub-device (Outdoor, Indoor, Wind, Rain, Solar, Soil, PM2.5, etc.)
#   appears here with a sanitised camelCase name.  See _capture_raw_fields().
# - Plugin version is now read dynamically from Info.plist (self.pluginVersion);
#   no separate Python constant.

import indigo
import math
import os as _os
import sys as _sys
import threading
import socket
from datetime import datetime
from urllib.parse import unquote

_sys.path.insert(0, _os.getcwd())
try:
    from plugin_utils import log_startup_banner
except ImportError:
    log_startup_banner = None
try:
    from plugin_utils import install_timestamp_filter
except ImportError:
    install_timestamp_filter = None

# Master secrets file — shared across all CliveS plugins. Optional: if absent
# or the key is missing, the plugin falls back to PluginConfig (expectedPasskey).
_sys.path.insert(0, "/Library/Application Support/Perceptive Automation")
try:
    from IndigoSecrets import ECOWITT_PASSKEY as _SECRETS_ECOWITT_PASSKEY
except ImportError:
    _SECRETS_ECOWITT_PASSKEY = ""

# ==============================================================================
# CONSTANTS
# ==============================================================================
HTTP_PORT        = 8088
LISTEN_ADDRESS   = "0.0.0.0"
UPDATE_FOLDER_ID = 0

DEVICE_TYPE_MAIN         = "ecowittMain"
DEVICE_TYPE_OUTDOOR      = "ecowittOutdoor"
DEVICE_TYPE_INDOOR       = "ecowittIndoor"
DEVICE_TYPE_WIND         = "ecowittWind"
DEVICE_TYPE_RAIN         = "ecowittRain"
DEVICE_TYPE_SOLAR        = "ecowittSolar"
DEVICE_TYPE_MULTICHANNEL = "ecowittMultiChannel"
DEVICE_TYPE_SOIL         = "ecowittSoil"
DEVICE_TYPE_PM25         = "ecowittPM25"
DEVICE_TYPE_LIGHTNING    = "ecowittLightning"
DEVICE_TYPE_LEAK         = "ecowittLeak"
DEVICE_TYPE_LDS          = "ecowittLDS"
DEVICE_TYPE_WH46         = "ecowittWH46"
DEVICE_TYPE_WH52         = "ecowittWH52"
DEVICE_TYPE_WN38         = "ecowittWN38"

WIND_CARDINALS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
]

# ==============================================================================
# MODULE-LEVEL STATE
# Controlled by menu toggle — persists for the lifetime of the plugin process.
# ==============================================================================
_TIMESTAMP_LOGGING = True


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def log(message, level="INFO"):
    """Custom log with optional [HH:MM:SS] timestamp prefix."""
    if _TIMESTAMP_LOGGING:
        indigo.server.log(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}", level=level)
    else:
        indigo.server.log(message, level=level)


def round_value(value, decimal_places=1):
    """Round a numeric value to specified decimal places, return as string."""
    try:
        return str(round(float(value), decimal_places))
    except Exception:
        return str(value)


def convert_temperature(fahrenheit, target_unit="C", decimal_places=1):
    """Convert Fahrenheit to C or F, return as string."""
    try:
        temp_f = float(fahrenheit)
        if target_unit == "F":
            return round_value(temp_f, decimal_places)
        return round_value((temp_f - 32.0) * 5.0 / 9.0, decimal_places)
    except Exception:
        return "0.0"


def convert_wind_speed(mph, target_unit="kmh", decimal_places=1):
    """Convert mph to selected wind unit, return as string."""
    try:
        speed_mph = float(mph)
        if target_unit == "mph":
            return round_value(speed_mph, decimal_places)
        elif target_unit == "kmh":
            return round_value(speed_mph * 1.60934, decimal_places)
        elif target_unit == "ms":
            return round_value(speed_mph * 0.44704, decimal_places)
        elif target_unit == "kts":
            return round_value(speed_mph * 0.868976, decimal_places)
        return round_value(speed_mph, decimal_places)
    except Exception:
        return "0.0"


def convert_pressure(inhg, target_unit="hPa", decimal_places=1):
    """Convert inHg to selected pressure unit, return as string."""
    try:
        p = float(inhg)
        if target_unit == "inHg":
            return round_value(p, decimal_places)
        elif target_unit in ("hPa", "mb"):
            return round_value(p * 33.8639, decimal_places)
        elif target_unit == "mmHg":
            return round_value(p * 25.4, decimal_places)
        return round_value(p, decimal_places)
    except Exception:
        return "0.0"


def convert_rain(inches, target_unit="mm", decimal_places=1):
    """Convert inches to mm or leave as inches, return as string."""
    try:
        rain_in = float(inches)
        if target_unit == "in":
            return round_value(rain_in, decimal_places)
        return round_value(rain_in * 25.4, decimal_places)
    except Exception:
        return "0.0"


def convert_distance(km, target_unit="km", decimal_places=1):
    """Convert km to miles or leave as km, return as string."""
    try:
        d = float(km)
        if target_unit == "mi":
            return round_value(d * 0.621371, decimal_places)
        return round_value(d, decimal_places)
    except Exception:
        return "0.0"


def get_unit_suffix(unit_type, target_unit):
    """Return display suffix string for a given unit type and target unit."""
    suffixes = {
        'temperature': {'C': 'degC',  'F': 'degF'},
        'wind':        {'mph': 'mph', 'kmh': 'km/h', 'ms': 'm/s', 'kts': 'kts'},
        'pressure':    {'inHg': 'inHg', 'hPa': 'hPa', 'mb': 'mb', 'mmHg': 'mmHg'},
        'rain':        {'in': 'in',   'mm': 'mm'},
        'distance':    {'km': 'km',   'mi': 'mi'}
    }
    return suffixes.get(unit_type, {}).get(target_unit, target_unit)


def get_wind_cardinal(degrees):
    """Convert 0-360 degrees to 16-point compass cardinal string."""
    try:
        idx = int((float(degrees) + 11.25) / 22.5) % 16
        return WIND_CARDINALS[idx]
    except Exception:
        return "N/A"


def calculate_vpd(temp_c, humidity_pct):
    """
    Calculate Vapour Pressure Deficit (kPa) from temperature (degC) and humidity (%).
    Uses Magnus/Tetens formula. Returns string to 2 decimal places.
    """
    try:
        t   = float(temp_c)
        rh  = float(humidity_pct)
        svp = 0.6108 * math.exp(17.27 * t / (t + 237.3))
        vpd = svp * (1.0 - rh / 100.0)
        return str(round(max(0.0, vpd), 2))
    except Exception:
        return "0.0"


def battery_to_percent(raw_value):
    """Normalise an Ecowitt battery payload field into a 0-100 percentage.

    Ecowitt uses two encodings depending on the sensor:
      * Binary flag (0 = OK, 1 = Low) — wh65batt, wh26batt, wh25batt, wh40batt,
        wh57batt, pm25batt1-4, leakbatt1-4, etc.
      * Voltage in volts (typical 1.2V flat / 1.6V full) — soilbatt1-16,
        tf_batt1-8, tempfbatt1-8, wh34batt1-8, wh35batt1-8, lds_batt, etc.

    Returns a 0-100 integer percentage suitable for Indigo's native batteryLevel
    property and our own `battery` custom state.
    """
    try:
        v = float(raw_value)
    except (TypeError, ValueError):
        return 0
    if v <= 1.0:
        # Binary: 0 = OK -> 100%, 1 = Low -> 0%
        return 100 if v == 0 else 0
    # Voltage: linear interpolation between 1.2V (dead) and 1.6V (full)
    pct = (v - 1.2) / 0.4 * 100.0
    return max(0, min(100, int(round(pct))))


# ==============================================================================
# PLUGIN CLASS
# ==============================================================================
class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super().__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        global _TIMESTAMP_LOGGING

        # -- Server config
        self.indigo_server_ip   = pluginPrefs.get("indigoServerIP", "")
        self.http_port          = int(pluginPrefs.get("httpPort", HTTP_PORT))
        self.listen_address     = pluginPrefs.get("listenAddress", LISTEN_ADDRESS)

        # -- Unit preferences
        self.temperature_unit   = pluginPrefs.get("temperatureUnit", "C")
        self.wind_speed_unit    = pluginPrefs.get("windSpeedUnit", "kmh")
        self.pressure_unit      = pluginPrefs.get("pressureUnit", "hPa")
        self.rain_unit          = pluginPrefs.get("rainUnit", "mm")
        self.distance_unit      = pluginPrefs.get("distanceUnit", "km")

        # -- Device settings
        self.auto_create        = pluginPrefs.get("autoCreateDevices", True)
        self.device_folder      = int(pluginPrefs.get("deviceFolder", UPDATE_FOLDER_ID))
        self.device_prefix      = pluginPrefs.get("devicePrefix", "Ecowitt")
        self.include_station_id = pluginPrefs.get("includeStationInName", False)

        # -- Data processing
        self.stale_timeout      = int(pluginPrefs.get("dataStaleTimeout", 300))
        self.decimal_places     = int(pluginPrefs.get("decimalPlaces", 1))
        self.battery_threshold  = int(pluginPrefs.get("batteryLowThreshold", 1))
        self.update_interval    = int(pluginPrefs.get("updateInterval", 30))

        # -- Pushover battery alerts
        self.pushover_enabled   = pluginPrefs.get("enablePushover", False)
        self.pushover_device    = pluginPrefs.get("pushoverDevice", "")

        # -- PASSKEY routing (optional). Blank = accept pushes from any gateway.
        # Resolution: IndigoSecrets.ECOWITT_PASSKEY -> PluginConfig field -> blank.
        # Set to a specific PASSKEY value to drop pushes from any other gateway
        # that happens to be uploading to this server. Comparison is exact and
        # case-sensitive (Ecowitt PASSKEYs are uppercase MAC-derived hex).
        self.expected_passkey   = ((_SECRETS_ECOWITT_PASSKEY or "").strip()
                                   or (pluginPrefs.get("expectedPasskey", "") or "").strip())

        # -- LDS01 water level sensor
        self.lds_enabled        = pluginPrefs.get("enableLDS", False)
        self.lds_tank_height    = int(pluginPrefs.get("ldsTankHeight", 1000))

        # -- Logging options
        self.debug              = pluginPrefs.get("showDebugInfo", False)
        self.log_raw_data       = pluginPrefs.get("logRawData", False)
        self.log_device_updates = pluginPrefs.get("logDeviceUpdates", False)
        _TIMESTAMP_LOGGING      = pluginPrefs.get("enableTimestampLogging", True)
        self.timestamp_enabled  = _TIMESTAMP_LOGGING

        # Install logging filter so self.logger.* calls also get the prefix.
        # The module-level log() helper continues to honour _TIMESTAMP_LOGGING
        # directly; toggleTimestampLogging() keeps both in sync.
        if install_timestamp_filter:
            self._ts_filter = install_timestamp_filter(self, enabled=self.timestamp_enabled)
        else:
            self._ts_filter = None

        # -- Runtime state
        self.server_thread      = None
        self.server_socket      = None
        self.server_running     = False
        self.last_data          = {}         # Last full payload received
        self.device_list        = {}         # device_key -> indigo device id
        self.last_update_time   = {}         # device id -> datetime
        self.stale_warned       = {}         # device id -> bool (one-shot warning)
        self.battery_alerted    = {}         # device id -> bool (one-shot Pushover)

        # -- Startup banner
        # Startup banner moved to showPluginInfo on demand (revised 25-May-2026 per Jay).


    # --------------------------------------------------------------------------
    # CONFIGURATION LOG
    # --------------------------------------------------------------------------
    def log_configuration(self):
        if self.debug:
            log("=== Ecowitt Plugin Configuration ===")
            log(f"  HTTP server:  {self.listen_address}:{self.http_port}")
            log(f"  Indigo IP:    {self.indigo_server_ip or 'Auto-detect'}")
            log(f"  Temperature:  {self.temperature_unit}")
            log(f"  Wind speed:   {self.wind_speed_unit}")
            log(f"  Pressure:     {self.pressure_unit}")
            log(f"  Rain:         {self.rain_unit}")
            log(f"  Distance:     {self.distance_unit}")
            log(f"  Auto-create:  {self.auto_create}")
            log(f"  Folder ID:    {self.device_folder}")
            log(f"  Prefix:       {self.device_prefix}")
            log(f"  Decimals:     {self.decimal_places}")
            log(f"  Stale limit:  {self.stale_timeout}s")
            log(f"  Pushover:     {'Enabled' if self.pushover_enabled else 'Disabled'}")
            if self.expected_passkey:
                src = "IndigoSecrets" if (_SECRETS_ECOWITT_PASSKEY or "").strip() else "PluginConfig"
                log(f"  PASSKEY:      {self.expected_passkey} (from {src})")
            else:
                log("  PASSKEY:      Any (no filter)")
            log(f"  LDS01:        {'Enabled' if self.lds_enabled else 'Disabled'}" +
                (f" (tank: {self.lds_tank_height}mm)" if self.lds_enabled else ""))
            log(f"  Timestamps:   {'Enabled' if _TIMESTAMP_LOGGING else 'Disabled'}")
            log("=====================================")


    def getFolderList(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Return list of device folders for the deviceFolder preference dropdown."""
        folder_list = [("0", "- Root (No Folder) -")]
        for folder in indigo.devices.folders:
            folder_list.append((str(folder.id), folder.name))
        return folder_list


    # --------------------------------------------------------------------------
    # PLUGIN LIFECYCLE
    # --------------------------------------------------------------------------
    def startup(self):
        log("Ecowitt Plugin starting up")
        self.log_configuration()
        self.start_http_server()


    def shutdown(self):
        log("Ecowitt Plugin shutting down")
        self.stop_http_server()


    def runConcurrentThread(self):
        """Indigo-managed thread: runs stale device check every 60 seconds."""
        try:
            while True:
                self.sleep(60)
                self.check_stale_devices()
        except self.StopThread:
            pass


    # --------------------------------------------------------------------------
    # HTTP SERVER
    # --------------------------------------------------------------------------
    def start_http_server(self):
        try:
            self.server_running = True
            self.server_thread  = threading.Thread(
                target=self.http_server_loop, daemon=True
            )
            self.server_thread.start()

            server_ip = self.indigo_server_ip or self.get_server_ip()
            log(f"HTTP server started on {self.listen_address}:{self.http_port}")
            log(f"Gateway settings: IP={server_ip}  Port={self.http_port}  Path=/data/report/  Protocol=Ecowitt")
        except Exception as e:
            log(f"Error starting HTTP server: {e}", "ERROR")


    def get_server_ip(self):
        """Detect the local IP address of the Indigo server."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "[Your Indigo Server IP]"


    def stop_http_server(self):
        self.server_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self.server_thread:
            self.server_thread.join(timeout=2)
        log("HTTP server stopped")


    def http_server_loop(self):
        """Main accept loop for the raw HTTP server socket."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.listen_address, self.http_port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)

            if self.debug:
                log(f"HTTP socket bound to {self.listen_address}:{self.http_port}")

            while self.server_running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    t = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    t.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.server_running:
                        log(f"Error accepting connection: {e}", "ERROR")

        except Exception as e:
            log(f"HTTP server fatal error: {e}", "ERROR")
        finally:
            if self.server_socket:
                try:
                    self.server_socket.close()
                except Exception:
                    pass


    def handle_client(self, client_socket, client_address):
        """Handle one incoming HTTP connection from the gateway."""
        try:
            request_data = b""
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                if b"\r\n\r\n" in request_data:
                    break

            request_str   = request_data.decode('utf-8', errors='replace')
            request_lines = request_str.split('\r\n')

            if self.debug:
                log(f"Request from {client_address[0]}")
            if self.log_raw_data:
                log(f"Raw request:\n{request_str}")

            if request_lines and request_lines[0].startswith("POST"):
                body_start = request_str.find("\r\n\r\n")
                if body_start != -1:
                    body        = request_str[body_start + 4:]
                    parsed_data = self.parse_post_data(body)
                    if parsed_data:
                        if self.log_raw_data:
                            log(f"Parsed fields: {parsed_data}")
                        self.process_weather_data(parsed_data)

            client_socket.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")

        except Exception as e:
            log(f"Error handling client: {e}", "ERROR")
        finally:
            client_socket.close()


    def parse_post_data(self, body):
        """Parse URL-encoded POST body from Ecowitt gateway into a dict."""
        try:
            params = {}
            for pair in body.strip().split('&'):
                if '=' in pair:
                    key, value      = pair.split('=', 1)
                    params[unquote(key)] = unquote(value)
            if self.debug:
                log(f"Parsed {len(params)} fields from gateway payload")
            return params
        except Exception as e:
            log(f"Error parsing POST data: {e}", "ERROR")
            return None


    # --------------------------------------------------------------------------
    # WEATHER DATA PROCESSING — dispatch to per-sensor updaters
    # --------------------------------------------------------------------------
    def process_weather_data(self, data):
        try:
            # PASSKEY routing: drop pushes from gateways other than the configured one
            if self.expected_passkey:
                incoming = str(data.get("PASSKEY", "")).strip()
                if incoming != self.expected_passkey:
                    if self.debug:
                        log(f"Rejected push from PASSKEY={incoming or '(missing)'} "
                            f"(expected {self.expected_passkey})", "WARNING")
                    return

            self.last_data = data

            if self.debug:
                log(f"Processing: station={data.get('stationtype', '?')} model={data.get('model', '?')}")

            self.update_main_device(data)

            if 'tempf' in data or 'humidity' in data:
                self.update_outdoor_device(data)

            if 'tempinf' in data or 'humidityin' in data:
                self.update_indoor_device(data)

            if 'windspeedmph' in data or 'winddir' in data:
                self.update_wind_device(data)

            if 'rainratein' in data or 'dailyrainin' in data:
                self.update_rain_device(data)

            if 'solarradiation' in data or 'uv' in data:
                self.update_solar_device(data)

            self.update_multichannel_devices(data)
            self.update_soil_devices(data)
            self.update_pm25_devices(data)

            if 'lightning_num' in data or 'lightning_time' in data:
                self.update_lightning_device(data)

            self.update_leak_devices(data)

            if self.lds_enabled:
                self.update_lds_device(data)

            # WH46 7-in-1 air quality (PM1 and PM4 distinguish from WH45)
            if 'pm1_co2' in data or 'pm4_co2' in data:
                self.update_wh46_device(data)

            self.update_wh52_devices(data)
            self.update_wn38_device(data)

        except Exception as e:
            log(f"Error processing weather data: {e}", "ERROR")


    # --------------------------------------------------------------------------
    # DEVICE UPDATERS
    # --------------------------------------------------------------------------
    def update_main_device(self, data):
        try:
            dev = self.get_or_create_device("Main Gateway", DEVICE_TYPE_MAIN, "main")
            if not dev:
                return

            now    = datetime.now()
            states = [
                {'key': 'stationType',      'value': str(data.get('stationtype', 'Unknown'))},
                {'key': 'model',            'value': str(data.get('model', 'Unknown'))},
                {'key': 'frequency',        'value': str(data.get('freq', 'Unknown'))},
                {'key': 'passkey',          'value': str(data.get('PASSKEY', 'Unknown'))},
                {'key': 'lastUpdate',       'value': str(data.get('dateutc', now.strftime('%Y-%m-%d %H:%M:%S')))},
                {'key': 'runtime',          'value': str(data.get('runtime', '0'))},
                {'key': 'interval',         'value': str(data.get('interval', 'Unknown'))},
                {'key': 'deviceOnline',     'value': True},
                {'key': 'connectionStatus', 'value': "Live"},
                {'key': 'lastUpdateAgeSec', 'value': 0}
            ]
            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = now
            self.stale_warned[dev.id]     = False

            # Catch-all: import every other payload field as a dynamic state on
            # the Main Gateway, so the Custom States panel surfaces ALL Ecowitt
            # data — including new fields added by future Ecowitt firmware
            # releases that this plugin doesn't yet know about.
            self._capture_raw_fields(dev, data)

        except Exception as e:
            log(f"Error updating main device: {e}", "ERROR")

    # ------------------------------------------------------------------
    # Dynamic-state catch-all (Main Gateway only)
    # ------------------------------------------------------------------
    # Ecowitt gateways send a moving target of fields depending on which
    # sensors are paired and the firmware version.  Hardcoding every key
    # in Devices.xml is a losing battle.  Instead, the plugin keeps a
    # per-device union of "fields seen so far" in pluginProps and exposes
    # every one as a dynamic Indigo state via getDeviceStateList().
    #
    # Three undocumented Indigo rules govern this (all caught the hard
    # way during Zigbee2MQTTBridge v1.7 development):
    #   1. State IDs must be camelCase ASCII (no underscores, despite
    #      XML allowing them).
    #   2. PluginProps keys cannot start with `_` (XML serialiser).
    #   3. PluginBase.getDeviceStateList returns a LIVE list reference;
    #      mutate a copy, never the original.
    # The helpers below honour all three.

    # Payload keys already handled by the curated typed-device updaters.
    # Anything in this set is NOT captured as a dynamic state — it is
    # surfaced on the typed sub-device with a friendly name and unit
    # conversion already applied.
    _MAIN_HANDLED_KEYS = {
        # Main device's own fields
        "stationtype", "model", "freq", "PASSKEY", "dateutc", "runtime",
        "interval",
        # Outdoor
        "tempf", "humidity", "dewptf",
        # Indoor
        "tempinf", "humidityin", "baromabsin", "baromrelin",
        # Wind
        "windspeedmph", "winddir", "windgustmph", "maxdailygust",
        "windspdmph_avg10m", "winddir_avg10m",
        # Rain
        "rainratein", "eventrainin", "hourlyrainin", "dailyrainin",
        "weeklyrainin", "monthlyrainin", "yearlyrainin", "totalrainin",
        # Solar / UV
        "solarradiation", "uv",
        # Lightning
        "lightning_num", "lightning_time", "lightning",
        # Battery flags handled per-typed-device
        "wh65batt", "wh25batt", "wh26batt", "wh40batt", "wh57batt",
        "wh68batt", "wh80batt", "wh90batt",
    }

    def _sanitise_state_key(self, key):
        """snake_case / mixed payload field name -> Indigo-safe camelCase ASCII.

        Indigo's XML serialiser rejects underscores, leading digits, leading
        underscores, and non-ASCII letters in state IDs.  We split on every
        non-alphanumeric and rebuild as camelCase.
        """
        if not key:
            return ""
        parts, cur = [], []
        for c in key:
            if c.isascii() and c.isalnum():
                cur.append(c)
            else:
                if cur:
                    parts.append("".join(cur))
                    cur = []
        if cur:
            parts.append("".join(cur))
        if not parts:
            return ""
        sk = parts[0][0].lower() + parts[0][1:] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
        if not sk[0].isalpha():
            sk = "z" + sk[:1].upper() + sk[1:]
        # Avoid Indigo's reserved native property names
        if sk in ("batteryLevel", "brightnessLevel", "onOffState", "sensorValue"):
            sk = "ec" + sk[:1].upper() + sk[1:]
        return sk

    def _is_valid_state_id(self, key):
        if not key or not key[0].isascii() or not key[0].isalpha():
            return False
        return all(c.isascii() and c.isalnum() for c in key)

    def _capture_raw_fields(self, dev, data):
        """Persist any Ecowitt payload field not already handled as a dynamic state."""
        if not isinstance(data, dict):
            return
        seen_csv = dev.pluginProps.get("seenDynamicKeys", "")
        seen = set(s for s in seen_csv.split(",") if s and self._is_valid_state_id(s))

        # Phase 1: identify pending writes + new keys (no I/O yet)
        pending = []      # [(state_key, state_val), ...]
        new_keys = []
        for raw_key, raw_val in data.items():
            if raw_key in self._MAIN_HANDLED_KEYS:
                continue
            if raw_val is None or raw_val == "":
                continue
            state_key = self._sanitise_state_key(raw_key)
            if not state_key or not self._is_valid_state_id(state_key):
                continue
            # Coerce
            try:
                fv = float(raw_val)
                state_val = fv if "." in str(raw_val) else int(fv)
            except (TypeError, ValueError):
                state_val = str(raw_val)[:512]
            pending.append((state_key, state_val))
            if state_key not in seen:
                seen.add(state_key)
                new_keys.append(state_key)

        # Phase 2: declare new keys BEFORE writing them (avoids one-off
        # "state key not defined" errors on first encounter).
        if new_keys:
            try:
                new_props = dict(dev.pluginProps)
                new_props["seenDynamicKeys"] = ",".join(sorted(seen))
                dev.replacePluginPropsOnServer(new_props)
                indigo.devices[dev.id].stateListOrDisplayStateIdChanged()
                log(f"Main Gateway: imported {len(new_keys)} new field(s): {new_keys}")
            except Exception as e:
                log(f"Main Gateway: dynamic-state refresh failed; rolling back. err={e}; "
                    f"new_keys={new_keys}", "ERROR")
                try:
                    rollback = dict(dev.pluginProps)
                    rollback["seenDynamicKeys"] = seen_csv
                    dev.replacePluginPropsOnServer(rollback)
                except Exception:
                    pass
                return

        # Phase 3: write all values (state IDs are now declared)
        for state_key, state_val in pending:
            try:
                dev.updateStateOnServer(state_key, state_val)
            except Exception as e:
                if self.debug:
                    log(f"Main Gateway: dynamic state '{state_key}' write failed: {e}", "WARNING")

    def getDeviceStateList(self, dev):
        """Add dynamic states to the Main Gateway state list."""
        original = indigo.PluginBase.getDeviceStateList(self, dev)
        if original is None or dev.deviceTypeId != DEVICE_TYPE_MAIN:
            return original
        # IMPORTANT: original is a LIVE reference to the parser's internal
        # cache.  Working on a list() copy avoids permanent corruption.
        state_list = list(original)
        seen_csv = dev.pluginProps.get("seenDynamicKeys", "")
        if not seen_csv:
            return state_list
        existing = set()
        try:
            for s in state_list:
                k = s.get("Key") if hasattr(s, "get") else s["Key"]
                if k:
                    existing.add(k)
        except Exception:
            existing = set()
        for key in seen_csv.split(","):
            key = key.strip()
            if not key or key in existing or not self._is_valid_state_id(key):
                continue
            label = key[:1].upper() + key[1:]
            current = dev.states.get(key) if hasattr(dev, "states") else None
            try:
                if isinstance(current, bool):
                    state_list.append(self.getDeviceStateDictForBoolTrueFalseType(key, label, label))
                elif isinstance(current, (int, float)):
                    state_list.append(self.getDeviceStateDictForNumberType(key, label, label))
                else:
                    state_list.append(self.getDeviceStateDictForStringType(key, label, label))
                existing.add(key)
            except Exception:
                continue
        return state_list


    def update_outdoor_device(self, data):
        try:
            station_id = str(data.get('PASSKEY', ''))
            dev        = self.get_or_create_device("Outdoor Sensor", DEVICE_TYPE_OUTDOOR, "outdoor", station_id)
            if not dev:
                return

            states = []
            temp_c = None  # Keep Celsius for VPD regardless of display unit

            if 'tempf' in data:
                states.append({'key': 'temperature',     'value': convert_temperature(data['tempf'], self.temperature_unit, self.decimal_places)})
                states.append({'key': 'temperatureUnit', 'value': get_unit_suffix('temperature', self.temperature_unit)})
                temp_c = (float(data['tempf']) - 32.0) * 5.0 / 9.0

            if 'humidity' in data:
                states.append({'key': 'humidity', 'value': str(data['humidity'])})

            if 'dewptf' in data:
                states.append({'key': 'dewPoint', 'value': convert_temperature(data['dewptf'], self.temperature_unit, self.decimal_places)})

            # VPD calculated from outdoor temp + humidity (no extra hardware)
            if temp_c is not None and 'humidity' in data:
                states.append({'key': 'vpd', 'value': calculate_vpd(temp_c, data['humidity'])})

            # Battery — HP2561 may report wh65batt, wh25batt, or wh26batt
            for batt_key in ('wh65batt', 'wh25batt', 'wh26batt'):
                if batt_key in data:
                    batt_level = data[batt_key]  # may be int (binary 0/1) or float (voltage)
                    batt_pct   = battery_to_percent(batt_level)
                    is_low     = batt_pct <= self.battery_threshold
                    states.append({'key': 'battery', 'value': batt_pct})
                    states.append({'key': 'batteryLow',   'value': is_low})
                    if is_low:
                        self.check_battery_alert(dev, "outdoor sensor")
                    break

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

            if self.log_device_updates:
                log(f"Updated {dev.name} ({len(states)} states)")

        except Exception as e:
            log(f"Error updating outdoor device: {e}", "ERROR")


    def update_indoor_device(self, data):
        try:
            dev = self.get_or_create_device("Indoor Sensor", DEVICE_TYPE_INDOOR, "indoor")
            if not dev:
                return

            states = []

            if 'tempinf' in data:
                states.append({'key': 'temperature',     'value': convert_temperature(data['tempinf'], self.temperature_unit, self.decimal_places)})
                states.append({'key': 'temperatureUnit', 'value': get_unit_suffix('temperature', self.temperature_unit)})

            if 'humidityin' in data:
                states.append({'key': 'humidity', 'value': str(data['humidityin'])})

            if 'baromabsin' in data:
                states.append({'key': 'pressureAbsolute',     'value': convert_pressure(data['baromabsin'], self.pressure_unit, self.decimal_places)})
                states.append({'key': 'pressureAbsoluteUnit', 'value': get_unit_suffix('pressure', self.pressure_unit)})

            if 'baromrelin' in data:
                states.append({'key': 'pressureRelative',     'value': convert_pressure(data['baromrelin'], self.pressure_unit, self.decimal_places)})
                states.append({'key': 'pressureRelativeUnit', 'value': get_unit_suffix('pressure', self.pressure_unit)})

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

            if self.log_device_updates:
                log(f"Updated {dev.name} ({len(states)} states)")

        except Exception as e:
            log(f"Error updating indoor device: {e}", "ERROR")


    def update_wind_device(self, data):
        try:
            station_id = str(data.get('PASSKEY', ''))
            dev        = self.get_or_create_device("Wind Sensor", DEVICE_TYPE_WIND, "wind", station_id)
            if not dev:
                return

            states = []

            if 'windspeedmph' in data:
                states.append({'key': 'windSpeed',     'value': convert_wind_speed(data['windspeedmph'], self.wind_speed_unit, self.decimal_places)})
                states.append({'key': 'windSpeedUnit', 'value': get_unit_suffix('wind', self.wind_speed_unit)})

            if 'winddir' in data:
                states.append({'key': 'windDirection',         'value': str(data['winddir'])})
                states.append({'key': 'windDirectionCardinal', 'value': get_wind_cardinal(data['winddir'])})

            if 'windgustmph' in data:
                states.append({'key': 'windGust', 'value': convert_wind_speed(data['windgustmph'], self.wind_speed_unit, self.decimal_places)})

            if 'maxdailygust' in data:
                states.append({'key': 'maxDailyGust', 'value': convert_wind_speed(data['maxdailygust'], self.wind_speed_unit, self.decimal_places)})

            if 'windchillf' in data:
                states.append({'key': 'windChill', 'value': convert_temperature(data['windchillf'], self.temperature_unit, self.decimal_places)})

            # Battery — covers WS80, WS90, WS85, WS68 variants
            for batt_key in ('wh80batt', 'ws90batt', 'ws85batt', 'wh68batt'):
                if batt_key in data:
                    batt_level = data[batt_key]  # may be int (binary 0/1) or float (voltage)
                    batt_pct   = battery_to_percent(batt_level)
                    is_low     = batt_pct <= self.battery_threshold
                    states.append({'key': 'battery', 'value': batt_pct})
                    states.append({'key': 'batteryLow',   'value': is_low})
                    if is_low:
                        self.check_battery_alert(dev, "wind sensor")
                    break

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

            if self.log_device_updates:
                log(f"Updated {dev.name} ({len(states)} states)")

        except Exception as e:
            log(f"Error updating wind device: {e}", "ERROR")


    def update_rain_device(self, data):
        try:
            dev = self.get_or_create_device("Rain Sensor", DEVICE_TYPE_RAIN, "rain")
            if not dev:
                return

            states = []

            for field, state_key in (
                ('rainratein',    'rainRate'),
                ('eventrainin',   'rainEvent'),
                ('hourlyrainin',  'rainHourly'),
                ('dailyrainin',   'rainDaily'),
                ('weeklyrainin',  'rainWeekly'),
                ('monthlyrainin', 'rainMonthly'),
                ('yearlyrainin',  'rainYearly'),
                ('totalrainin',   'rainTotal'),
            ):
                if field in data:
                    states.append({'key': state_key, 'value': convert_rain(data[field], self.rain_unit, self.decimal_places)})

            states.append({'key': 'rainUnit', 'value': get_unit_suffix('rain', self.rain_unit)})

            if 'wh40batt' in data:
                batt_level = int(data['wh40batt'])
                batt_pct   = battery_to_percent(batt_level)
                is_low     = batt_pct <= self.battery_threshold
                states.append({'key': 'battery', 'value': batt_pct})
                states.append({'key': 'batteryLow',   'value': is_low})
                if is_low:
                    self.check_battery_alert(dev, "rain sensor")

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

            if self.log_device_updates:
                log(f"Updated {dev.name} ({len(states)} states)")

        except Exception as e:
            log(f"Error updating rain device: {e}", "ERROR")


    def update_solar_device(self, data):
        try:
            dev = self.get_or_create_device("Solar/UV Sensor", DEVICE_TYPE_SOLAR, "solar")
            if not dev:
                return

            states = []

            if 'solarradiation' in data:
                states.append({'key': 'solarRadiation', 'value': round_value(data['solarradiation'], self.decimal_places)})
                states.append({'key': 'solarUnit',      'value': 'W/m2'})

            if 'uv' in data:
                states.append({'key': 'uvIndex', 'value': str(data['uv'])})

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

        except Exception as e:
            log(f"Error updating solar device: {e}", "ERROR")


    def update_multichannel_devices(self, data):
        """WH31 / WN31 multi-channel temperature and humidity sensors (up to 8)."""
        try:
            for ch in range(1, 9):
                temp_key = f"temp{ch}f"
                hum_key  = f"humidity{ch}"
                batt_key = f"batt{ch}"

                if temp_key not in data and hum_key not in data:
                    continue

                dev = self.get_or_create_device(f"Multi-Channel {ch}", DEVICE_TYPE_MULTICHANNEL, f"multichannel_{ch}")
                if not dev:
                    continue

                states = [{'key': 'channel', 'value': str(ch)}]

                if temp_key in data:
                    states.append({'key': 'temperature',     'value': convert_temperature(data[temp_key], self.temperature_unit, self.decimal_places)})
                    states.append({'key': 'temperatureUnit', 'value': get_unit_suffix('temperature', self.temperature_unit)})

                if hum_key in data:
                    states.append({'key': 'humidity', 'value': str(data[hum_key])})

                if batt_key in data:
                    batt_level = data[batt_key]  # may be int (binary 0/1) or float (voltage)
                    batt_pct   = battery_to_percent(batt_level)
                    is_low     = batt_pct <= self.battery_threshold
                    states.append({'key': 'battery', 'value': batt_pct})
                    states.append({'key': 'batteryLow',   'value': is_low})
                    if is_low:
                        self.check_battery_alert(dev, f"multi-channel sensor {ch}")

                states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                states.append({'key': 'deviceOnline', 'value': True})

                dev.updateStatesOnServer(states)
                self.last_update_time[dev.id] = datetime.now()
                self.stale_warned[dev.id]     = False

        except Exception as e:
            log(f"Error updating multi-channel devices: {e}", "ERROR")


    def update_soil_devices(self, data):
        """WH51 soil moisture sensors (up to 8 channels)."""
        try:
            for sensor in range(1, 9):
                m_key    = f"soilmoisture{sensor}"
                batt_key = f"soilbatt{sensor}"

                if m_key not in data:
                    continue

                dev = self.get_or_create_device(f"Soil Sensor {sensor}", DEVICE_TYPE_SOIL, f"soil_{sensor}")
                if not dev:
                    continue

                states = [
                    {'key': 'sensorNumber', 'value': str(sensor)},
                    {'key': 'moisture',     'value': str(data[m_key])},
                    {'key': 'moistureUnit', 'value': '%'}
                ]

                if batt_key in data:
                    # soilbatt* is voltage (e.g. 1.5) — keep as float, don't truncate
                    batt_pct = battery_to_percent(data[batt_key])
                    states.append({'key': 'battery', 'value': batt_pct})

                states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                states.append({'key': 'deviceOnline', 'value': True})

                dev.updateStatesOnServer(states)
                self.last_update_time[dev.id] = datetime.now()
                self.stale_warned[dev.id]     = False

        except Exception as e:
            log(f"Error updating soil devices: {e}", "ERROR")


    def update_pm25_devices(self, data):
        """WH41 / WH43 / WH45 PM2.5 air quality sensors (up to 4 channels)."""
        try:
            for sensor in range(1, 5):
                pm_key     = f"pm25_{sensor}"
                pm_avg_key = f"pm25_24h_{sensor}"
                batt_key   = f"pm25batt{sensor}"

                if pm_key not in data:
                    continue

                dev = self.get_or_create_device(f"PM2.5 Sensor {sensor}", DEVICE_TYPE_PM25, f"pm25_{sensor}")
                if not dev:
                    continue

                states = [
                    {'key': 'sensorNumber', 'value': str(sensor)},
                    {'key': 'pm25',         'value': str(data[pm_key])},
                    {'key': 'pm25Unit',     'value': 'ug/m3'}
                ]

                if pm_avg_key in data:
                    states.append({'key': 'pm25_24h', 'value': str(data[pm_avg_key])})

                if batt_key in data:
                    batt_level = data[batt_key]  # may be int (binary 0/1) or float (voltage)
                    batt_pct   = battery_to_percent(batt_level)
                    is_low     = batt_pct <= self.battery_threshold
                    states.append({'key': 'battery', 'value': batt_pct})
                    states.append({'key': 'batteryLow',   'value': is_low})
                    if is_low:
                        self.check_battery_alert(dev, f"PM2.5 sensor {sensor}")

                states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                states.append({'key': 'deviceOnline', 'value': True})

                dev.updateStatesOnServer(states)
                self.last_update_time[dev.id] = datetime.now()
                self.stale_warned[dev.id]     = False

            # WH45 all-in-one CO2 + PM2.5/PM10 sensor
            if any(k in data for k in ('pm25_co2', 'pm10_co2', 'co2')):
                # Only create WH45 device if WH46-specific fields are absent
                if 'pm1_co2' not in data and 'pm4_co2' not in data:
                    dev    = self.get_or_create_device("WH45 Air Quality", DEVICE_TYPE_PM25, "wh45")
                    states = []
                    if 'pm25_co2' in data:
                        states.append({'key': 'pm25', 'value': str(data['pm25_co2'])})
                    if 'pm10_co2' in data:
                        states.append({'key': 'pm10', 'value': str(data['pm10_co2'])})
                    if 'co2' in data:
                        states.append({'key': 'co2',     'value': str(data['co2'])})
                        states.append({'key': 'co2Unit', 'value': 'ppm'})
                    if states and dev:
                        states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                        states.append({'key': 'deviceOnline', 'value': True})
                        dev.updateStatesOnServer(states)
                        self.last_update_time[dev.id] = datetime.now()

        except Exception as e:
            log(f"Error updating PM2.5 devices: {e}", "ERROR")


    def update_lightning_device(self, data):
        """WH57 lightning detector."""
        try:
            dev = self.get_or_create_device("Lightning Sensor", DEVICE_TYPE_LIGHTNING, "lightning")
            if not dev:
                return

            states = []

            if 'lightning_num' in data:
                states.append({'key': 'strikeCount', 'value': str(data['lightning_num'])})

            if 'lightning' in data:
                states.append({'key': 'distance',     'value': convert_distance(data['lightning'], self.distance_unit, self.decimal_places)})
                states.append({'key': 'distanceUnit', 'value': get_unit_suffix('distance', self.distance_unit)})

            if 'lightning_time' in data:
                states.append({'key': 'lastStrike', 'value': str(data['lightning_time'])})

            if 'wh57batt' in data:
                batt_level = int(data['wh57batt'])
                batt_pct   = battery_to_percent(batt_level)
                is_low     = batt_pct <= self.battery_threshold
                states.append({'key': 'battery', 'value': batt_pct})
                states.append({'key': 'batteryLow',   'value': is_low})
                if is_low:
                    self.check_battery_alert(dev, "lightning sensor")

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

        except Exception as e:
            log(f"Error updating lightning device: {e}", "ERROR")


    def update_leak_devices(self, data):
        """WH55 water leak sensors (up to 4 channels)."""
        try:
            for sensor in range(1, 5):
                leak_key = f"leak{sensor}"
                batt_key = f"leakbatt{sensor}"

                if leak_key not in data:
                    continue

                dev = self.get_or_create_device(f"Leak Sensor {sensor}", DEVICE_TYPE_LEAK, f"leak_{sensor}")
                if not dev:
                    continue

                leak_value  = str(data[leak_key])
                leak_status = "Leak Detected" if leak_value == "1" else "No Leak"

                states = [
                    {'key': 'sensorNumber', 'value': str(sensor)},
                    {'key': 'leakStatus',   'value': leak_status},
                    {'key': 'leakDetected', 'value': leak_value == "1"}
                ]

                if batt_key in data:
                    batt_level = data[batt_key]  # may be int (binary 0/1) or float (voltage)
                    batt_pct   = battery_to_percent(batt_level)
                    is_low     = batt_pct <= self.battery_threshold
                    states.append({'key': 'battery', 'value': batt_pct})
                    states.append({'key': 'batteryLow',   'value': is_low})
                    if is_low:
                        self.check_battery_alert(dev, f"leak sensor {sensor}")

                states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                states.append({'key': 'deviceOnline', 'value': True})

                dev.updateStatesOnServer(states)
                self.last_update_time[dev.id] = datetime.now()
                self.stale_warned[dev.id]     = False

        except Exception as e:
            log(f"Error updating leak devices: {e}", "ERROR")


    def update_lds_device(self, data):
        """
        LDS01 / LDS04 (WH54) laser distance sensor for water level monitoring.
        Converts raw distance (mm from sensor to surface) into water level using
        configured tank height.
        """
        try:
            dist_mm = None
            for field in ('ldsdistance', 'distance', 'lds_distance'):
                if field in data:
                    dist_mm = float(data[field])
                    break

            if dist_mm is None:
                return  # No LDS data in this payload

            dev = self.get_or_create_device("Water Level Sensor", DEVICE_TYPE_LDS, "lds")
            if not dev:
                return

            tank_h    = float(self.lds_tank_height)
            water_mm  = max(0.0, tank_h - dist_mm)
            water_pct = min(100.0, max(0.0, (water_mm / tank_h) * 100.0)) if tank_h > 0 else 0.0

            states = [
                {'key': 'distanceMm',    'value': str(round(dist_mm, 1))},
                {'key': 'waterLevelMm',  'value': str(round(water_mm, 1))},
                {'key': 'waterLevelPct', 'value': str(round(water_pct, 1))},
                {'key': 'tankHeightMm',  'value': str(int(tank_h))},
                {'key': 'lastUpdate',    'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                {'key': 'deviceOnline',  'value': True}
            ]

            if 'ldsbatt' in data:
                # ldsbatt is a voltage (e.g. 1.5); battery_to_percent does its own
                # guarded float() — int("1.5") would raise ValueError and abort the update.
                batt_pct   = battery_to_percent(data['ldsbatt'])
                is_low     = batt_pct <= self.battery_threshold
                states.append({'key': 'battery', 'value': batt_pct})
                states.append({'key': 'batteryLow',   'value': is_low})
                if is_low:
                    self.check_battery_alert(dev, "water level sensor")

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()
            self.stale_warned[dev.id]     = False

            if self.log_device_updates:
                log(f"Updated {dev.name}: {water_pct:.1f}% full ({water_mm:.0f}mm of {tank_h:.0f}mm)")

        except Exception as e:
            log(f"Error updating LDS water level device: {e}", "ERROR")


    def update_wh46_device(self, data):
        """
        WH46 7-in-1 indoor air quality sensor.
        Reports PM1, PM2.5, PM4, PM10, CO2 plus internal temp and humidity.
        Identified by presence of pm1_co2 or pm4_co2 fields.
        """
        try:
            dev = self.get_or_create_device("WH46 Air Quality", DEVICE_TYPE_WH46, "wh46")
            if not dev:
                return

            states = []
            for field, state_key in (
                ('pm1_co2',  'pm1'),
                ('pm25_co2', 'pm25'),
                ('pm4_co2',  'pm4'),
                ('pm10_co2', 'pm10'),
                ('co2in',    'co2'),
                ('tf_co2',   'temperature'),
                ('humi_co2', 'humidity'),
            ):
                if field in data:
                    states.append({'key': state_key, 'value': str(data[field])})

            if states:
                states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                states.append({'key': 'deviceOnline', 'value': True})
                dev.updateStatesOnServer(states)
                self.last_update_time[dev.id] = datetime.now()

        except Exception as e:
            log(f"Error updating WH46 device: {e}", "ERROR")


    def update_wh52_devices(self, data):
        """
        WH52 soil moisture + temperature + EC sensors.
        Identified by presence of soilec fields (WH51 does not send EC).
        """
        try:
            for sensor in range(1, 9):
                ec_key = f"soilec{sensor}"
                if ec_key not in data:
                    continue  # WH52 sends EC; WH51 does not

                m_key = f"soilmoisture{sensor}"
                t_key = f"soiltemp{sensor}f"
                dev   = self.get_or_create_device(f"Soil Sensor {sensor} (WH52)", DEVICE_TYPE_WH52, f"wh52_{sensor}")
                if not dev:
                    continue

                states = [{'key': 'sensorNumber', 'value': str(sensor)}]

                if m_key in data:
                    states.append({'key': 'moisture',     'value': str(data[m_key])})
                    states.append({'key': 'moistureUnit', 'value': '%'})

                if t_key in data:
                    states.append({'key': 'temperature',     'value': convert_temperature(data[t_key], self.temperature_unit, self.decimal_places)})
                    states.append({'key': 'temperatureUnit', 'value': get_unit_suffix('temperature', self.temperature_unit)})

                states.append({'key': 'ec',          'value': str(data[ec_key])})
                states.append({'key': 'ecUnit',      'value': 'uS/cm'})
                states.append({'key': 'lastUpdate',  'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                states.append({'key': 'deviceOnline','value': True})

                dev.updateStatesOnServer(states)
                self.last_update_time[dev.id] = datetime.now()

        except Exception as e:
            log(f"Error updating WH52 devices: {e}", "ERROR")


    def update_wn38_device(self, data):
        """
        WN38 Black Globe Thermometer / WBGT sensor (heat stress monitoring).
        Field names are tentative for this newer sensor — check debug log if no data.
        """
        try:
            # Check known / likely field names for WN38
            bgt_val  = data.get('bgt')
            wbgt_val = data.get('wbgt')

            if bgt_val is None and wbgt_val is None:
                return

            dev = self.get_or_create_device("WN38 WBGT Sensor", DEVICE_TYPE_WN38, "wn38")
            if not dev:
                return

            states = []

            if bgt_val is not None:
                states.append({'key': 'blackGlobeTemp',     'value': convert_temperature(bgt_val, self.temperature_unit, self.decimal_places)})
                states.append({'key': 'blackGlobeTempUnit', 'value': get_unit_suffix('temperature', self.temperature_unit)})

            if wbgt_val is not None:
                states.append({'key': 'wbgt',     'value': convert_temperature(wbgt_val, self.temperature_unit, self.decimal_places)})
                states.append({'key': 'wbgtUnit', 'value': get_unit_suffix('temperature', self.temperature_unit)})

            states.append({'key': 'lastUpdate',   'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            states.append({'key': 'deviceOnline', 'value': True})

            dev.updateStatesOnServer(states)
            self.last_update_time[dev.id] = datetime.now()

        except Exception as e:
            log(f"Error updating WN38 device: {e}", "ERROR")


    # --------------------------------------------------------------------------
    # STALE DEVICE DETECTION
    # --------------------------------------------------------------------------
    def check_stale_devices(self):
        """
        Called every 60 seconds from runConcurrentThread.
        Marks any device offline if no data received within stale_timeout seconds.
        Issues a one-shot warning per device to avoid log spam.

        For the Main Gateway device, also refreshes connectionStatus
        (Live / Stale) and lastUpdateAgeSec on every tick — gives a constantly-
        current view of feed freshness without waiting for the stale threshold.
        """
        try:
            now = datetime.now()
            for dev_key, dev_id in list(self.device_list.items()):
                if dev_id not in indigo.devices:
                    continue

                last_seen = self.last_update_time.get(dev_id)
                if last_seen is None:
                    continue

                dev   = indigo.devices[dev_id]
                age_s = int((now - last_seen).total_seconds())
                stale = age_s > self.stale_timeout

                if stale:
                    if not self.stale_warned.get(dev_id, False):
                        log(f"[!] No data from {dev.name} for {age_s // 60} min — marking offline", "WARNING")
                        self.stale_warned[dev_id] = True
                    try:
                        dev.updateStateOnServer("deviceOnline", False)
                    except Exception:
                        pass

                # Main Gateway: keep connectionStatus and age fresh every tick
                if dev.deviceTypeId == DEVICE_TYPE_MAIN:
                    try:
                        dev.updateStatesOnServer([
                            {'key': 'connectionStatus', 'value': "Stale" if stale else "Live"},
                            {'key': 'lastUpdateAgeSec', 'value': age_s}
                        ])
                    except Exception:
                        pass

        except Exception as e:
            log(f"Error in stale device check: {e}", "ERROR")


    # --------------------------------------------------------------------------
    # PUSHOVER BATTERY ALERTS
    # --------------------------------------------------------------------------
    def check_battery_alert(self, dev, sensor_label):
        """
        Send a one-shot Pushover alert when battery goes low.
        Alert is suppressed for the remainder of the plugin session once sent.
        Reset is only on plugin restart, not when battery recovers.
        """
        if not self.pushover_enabled:
            return
        if self.battery_alerted.get(dev.id, False):
            return  # Already alerted for this device this session

        sent = self.send_pushover_alert(
            title   = "Ecowitt Low Battery",
            message = f"Low battery on {dev.name} ({sensor_label})"
        )
        if sent:
            # Only latch the one-shot once the send actually succeeded, so a failed
            # send is retried next cycle rather than silently suppressed forever.
            self.battery_alerted[dev.id] = True
            log(f"[!] Low battery Pushover alert sent for {dev.name}", "WARNING")


    def send_pushover_alert(self, title, message):
        """Send a Pushover notification via the Pushover Indigo plugin. Returns True if sent."""
        try:
            plugin = indigo.server.getPlugin("io.thechad.indigoplugin.pushover")
            if not plugin or not plugin.isEnabled():
                log("Pushover plugin is not enabled — cannot send alert", "WARNING")
                return False

            # Action id is "send" (NOT "sendPushover"), and props use the msg* keys
            # the Pushover plugin actually reads; msgPriority must be a string.
            props = {"msgTitle": title, "msgBody": message, "msgPriority": "0"}
            if self.pushover_device:
                props["msgDevice"] = self.pushover_device

            plugin.executeAction("send", props=props)
            return True

        except Exception as e:
            log(f"Error sending Pushover alert: {e}", "ERROR")
            return False


    # --------------------------------------------------------------------------
    # DEVICE MANAGEMENT
    # --------------------------------------------------------------------------
    def get_or_create_device(self, name, device_type, device_id, station_id=""):
        """
        Return an existing Indigo device or create a new one.
        Maintains an in-memory cache (self.device_list) keyed by device_id string.
        """
        try:
            # Check cache first
            if device_id in self.device_list:
                cached_id = self.device_list[device_id]
                if cached_id in indigo.devices:
                    return indigo.devices[cached_id]

            full_name = self.build_device_name(name, station_id)

            # Search existing Indigo devices by name
            for dev in indigo.devices.iter(f"self.{device_type}"):
                if dev.name == full_name:
                    self.device_list[device_id] = dev.id
                    return dev

            # Auto-create disabled — do not create
            if not self.auto_create:
                if self.debug:
                    log(f"Auto-create disabled — '{full_name}' not found")
                return None

            # Create new device
            log(f"Creating device: {full_name}")
            folder_id = self.device_folder if self.device_folder != 0 else None
            new_dev   = indigo.device.create(
                protocol     = indigo.kProtocol.Plugin,
                address      = device_id,
                name         = full_name,
                description  = f"{self.device_prefix} {name}",
                pluginId     = self.pluginId,
                deviceTypeId = device_type,
                folder       = folder_id
            )
            self.device_list[device_id] = new_dev.id
            return new_dev

        except Exception as e:
            log(f"Error getting/creating device '{name}': {e}", "ERROR")
            return None


    def build_device_name(self, base_name, station_id=""):
        """Construct full device name from prefix, base name and optional station ID."""
        parts = []
        if self.device_prefix:
            parts.append(self.device_prefix)
        parts.append(base_name)
        if self.include_station_id and station_id:
            short_id = station_id[-6:] if len(station_id) > 6 else station_id
            parts.append(f"[{short_id}]")
        return " ".join(parts)


    def deviceStartComm(self, dev):
        log(f"Device started: {dev.name}")
        # Re-pull the state schema from Devices.xml.  Existing devices created
        # before a Devices.xml schema change still have the old state slots in
        # the Indigo database, so a write to a newly-renamed state (e.g. v2.1.0
        # rename batteryLevel -> battery) raises "state key not defined" until
        # the device's slots are refreshed.  Calling stateListOrDisplay here
        # makes the new schema take effect immediately on plugin reload.
        try:
            dev.stateListOrDisplayStateIdChanged()
        except Exception as e:
            if self.debug:
                log(f"{dev.name}: stateListOrDisplay refresh failed: {e}", "WARNING")
        try:
            dev.updateStateOnServer("deviceOnline", True)
        except Exception:
            pass


    def deviceStopComm(self, dev):
        log(f"Device stopped: {dev.name}")
        try:
            dev.updateStateOnServer("deviceOnline", False)
        except Exception:
            pass


    @staticmethod
    def didDeviceCommPropertyChange(oldDevice, newDevice):
        """Suppress unnecessary deviceStopComm/deviceStartComm cycles.

        Devices in this plugin are created and updated internally from the
        gateway push feed; none of the user-editable pluginProps justify a
        comm restart. Returning False prevents Indigo from cycling comm on
        every internal replacePluginPropsOnServer write.
        """
        return False


    # --------------------------------------------------------------------------
    # PREFERENCES
    # --------------------------------------------------------------------------
    def validatePrefsConfigUi(self, valuesDict):
        errorDict = indigo.Dict()

        ip = valuesDict.get("indigoServerIP", "").strip()
        if ip:
            parts = ip.split('.')
            if len(parts) != 4:
                errorDict["indigoServerIP"] = "Must be in format: xxx.xxx.xxx.xxx"
            else:
                try:
                    if not all(0 <= int(p) <= 255 for p in parts):
                        errorDict["indigoServerIP"] = "Each number must be 0-255"
                except ValueError:
                    errorDict["indigoServerIP"] = "Must contain only numbers and dots"

        try:
            port = int(valuesDict.get("httpPort", HTTP_PORT))
            if not (1024 <= port <= 65535):
                errorDict["httpPort"] = "Port must be 1024-65535"
        except ValueError:
            errorDict["httpPort"] = "Port must be a valid number"

        if not valuesDict.get("devicePrefix", "").strip():
            errorDict["devicePrefix"] = "Device prefix cannot be empty"

        try:
            t = int(valuesDict.get("dataStaleTimeout", 300))
            if t < 60:
                errorDict["dataStaleTimeout"] = "Timeout must be at least 60 seconds"
        except ValueError:
            errorDict["dataStaleTimeout"] = "Must be a valid number"

        try:
            h = int(valuesDict.get("ldsTankHeight", 1000))
            if h <= 0:
                errorDict["ldsTankHeight"] = "Tank height must be greater than 0mm"
        except ValueError:
            errorDict["ldsTankHeight"] = "Must be a valid number (mm)"

        if len(errorDict) > 0:
            return (False, valuesDict, errorDict)
        return (True, valuesDict)


    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        global _TIMESTAMP_LOGGING
        if userCancelled:
            return

        old_port    = self.http_port
        old_address = self.listen_address

        self.indigo_server_ip   = valuesDict.get("indigoServerIP", "")
        self.http_port          = int(valuesDict.get("httpPort", HTTP_PORT))
        self.listen_address     = valuesDict.get("listenAddress", LISTEN_ADDRESS)

        self.temperature_unit   = valuesDict.get("temperatureUnit", "C")
        self.wind_speed_unit    = valuesDict.get("windSpeedUnit", "kmh")
        self.pressure_unit      = valuesDict.get("pressureUnit", "hPa")
        self.rain_unit          = valuesDict.get("rainUnit", "mm")
        self.distance_unit      = valuesDict.get("distanceUnit", "km")

        self.auto_create        = valuesDict.get("autoCreateDevices", True)
        self.device_folder      = int(valuesDict.get("deviceFolder", UPDATE_FOLDER_ID))
        self.device_prefix      = valuesDict.get("devicePrefix", "Ecowitt")
        self.include_station_id = valuesDict.get("includeStationInName", False)

        self.stale_timeout      = int(valuesDict.get("dataStaleTimeout", 300))
        self.decimal_places     = int(valuesDict.get("decimalPlaces", 1))
        self.battery_threshold  = int(valuesDict.get("batteryLowThreshold", 1))
        self.update_interval    = int(valuesDict.get("updateInterval", 30))

        self.pushover_enabled   = valuesDict.get("enablePushover", False)
        self.pushover_device    = valuesDict.get("pushoverDevice", "")

        self.expected_passkey   = ((_SECRETS_ECOWITT_PASSKEY or "").strip()
                                   or (valuesDict.get("expectedPasskey", "") or "").strip())

        self.lds_enabled        = valuesDict.get("enableLDS", False)
        self.lds_tank_height    = int(valuesDict.get("ldsTankHeight", 1000))

        self.debug              = valuesDict.get("showDebugInfo", False)
        self.log_raw_data       = valuesDict.get("logRawData", False)
        self.log_device_updates = valuesDict.get("logDeviceUpdates", False)
        _TIMESTAMP_LOGGING      = valuesDict.get("enableTimestampLogging", True)

        log("Preferences updated")
        self.log_configuration()

        if old_port != self.http_port or old_address != self.listen_address:
            log("HTTP server settings changed — restarting")
            self.stop_http_server()
            self.start_http_server()

        if not self.auto_create:
            log("[!] Auto-create disabled — new sensors will not create devices automatically", "WARNING")


    # --------------------------------------------------------------------------
    # MENU ITEM HANDLERS
    # --------------------------------------------------------------------------
    def toggleTimestampLogging(self):
        """Menu: Toggle [HH:MM:SS.mmm] timestamp prefix on all log output.

        Flips both the module-level _TIMESTAMP_LOGGING flag (used by the log()
        helper) and the self.logger filter installed in __init__ so every log
        line gains/loses the prefix together.
        """
        global _TIMESTAMP_LOGGING
        _TIMESTAMP_LOGGING = not _TIMESTAMP_LOGGING
        self.timestamp_enabled = _TIMESTAMP_LOGGING
        if self._ts_filter:
            self._ts_filter.enabled = _TIMESTAMP_LOGGING
        self.pluginPrefs["enableTimestampLogging"] = _TIMESTAMP_LOGGING
        indigo.server.savePluginPrefs()
        state_str = "ON" if _TIMESTAMP_LOGGING else "OFF"
        indigo.server.log(f"[{self.pluginDisplayName}] Timestamps in Log -> {state_str}")


    def toggleLDSSensor(self):
        """Menu: Enable or disable LDS01/LDS04 water level sensor support."""
        self.lds_enabled = not self.lds_enabled
        self.pluginPrefs["enableLDS"] = self.lds_enabled
        indigo.server.savePluginPrefs()
        state_str = "enabled" if self.lds_enabled else "disabled"
        log(f"LDS01 Water Level Sensor {state_str}")
        if self.lds_enabled:
            log(f"  Tank height configured: {self.lds_tank_height}mm  (change in Plugin Preferences)")


    def togglePushoverAlerts(self):
        """Menu: Enable or disable Pushover battery low alerts."""
        self.pushover_enabled = not self.pushover_enabled
        self.pluginPrefs["enablePushover"] = self.pushover_enabled
        indigo.server.savePluginPrefs()
        state_str = "enabled" if self.pushover_enabled else "disabled"
        log(f"Pushover battery alerts {state_str}")
        if self.pushover_enabled and not self.pushover_device:
            log("[!] Pushover device name not set — alerts will use default device. Set in Plugin Preferences.", "WARNING")


    def showPluginInfo(self, valuesDict=None, typeId=None):
        """Menu: Re-run the startup banner on demand."""
        extras = [
            ("Compatible Hardware:", "Ecowitt / Fine Offset / Ambient / Froggit / Aercus / Bresser"),
            ("Timestamps in Log:",   "ON" if self.timestamp_enabled else "OFF"),
        ]
        if log_startup_banner:
            log_startup_banner(self.pluginId, self.pluginDisplayName, self.pluginVersion, extras=extras)
        else:
            indigo.server.log(f"{self.pluginDisplayName} v{self.pluginVersion}")
            for label, value in extras:
                indigo.server.log(f"  {label} {value}")


    def showPluginStatus(self):
        """Menu: Display current plugin status and configuration to the Indigo log."""
        log("=== Ecowitt Plugin Status ===")
        log(f"  Version:       {self.pluginVersion}")
        log(f"  HTTP server:   {self.listen_address}:{self.http_port}  ({'running' if self.server_running else 'STOPPED'})")
        log(f"  Indigo IP:     {self.indigo_server_ip or 'Auto-detect'}")
        log(f"  Units:         temp={self.temperature_unit}  wind={self.wind_speed_unit}  pressure={self.pressure_unit}  rain={self.rain_unit}")
        log(f"  Devices known: {len(self.device_list)}")
        log(f"  Last payload:  {len(self.last_data)} fields from gateway")
        log(f"  Stale timeout: {self.stale_timeout}s")
        log(f"  Auto-create:   {'Yes' if self.auto_create else 'No'}")
        log(f"  Pushover:      {'Enabled' if self.pushover_enabled else 'Disabled'}")
        log(f"  LDS01:         {'Enabled' if self.lds_enabled else 'Disabled'}" +
            (f" (tank: {self.lds_tank_height}mm)" if self.lds_enabled else ""))
        log(f"  Timestamps:    {'Enabled' if _TIMESTAMP_LOGGING else 'Disabled'}")
        log(f"  Debug:         {'Enabled' if self.debug else 'Disabled'}")
        if self.last_data:
            model = self.last_data.get('model', 'Unknown')
            stype = self.last_data.get('stationtype', 'Unknown')
            log(f"  Gateway model: {model}  ({stype})")
        log("=============================")


    def refreshAllDevices(self):
        """Menu: Re-process the last received payload to refresh all device states."""
        if not self.last_data:
            log("No data received yet — nothing to refresh", "WARNING")
            return
        log(f"Refreshing all devices from last received payload ({len(self.last_data)} fields)")
        self.process_weather_data(self.last_data)
