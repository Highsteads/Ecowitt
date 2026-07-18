#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_plugin.py
# Description: Unit tests for the Ecowitt plugin — pure conversion/math helpers,
#              battery decoding, LDS water-level maths and config-coercion guards.
#              Runs with no Indigo runtime (indigo is stubbed before import).
# Author:      CliveS & Claude Fable 5
# Date:        18-07-2026
# Version:     1.0
#
# Run:  python3 -m pytest test_plugin.py -q   (Indigo's Python 3.13)

import sys
import types
from unittest.mock import MagicMock

import pytest

# --------------------------------------------------------------------------
# Stub the indigo runtime so plugin.py imports standalone.
# --------------------------------------------------------------------------
_ind = types.ModuleType("indigo")


class _PluginBase:
    def __init__(self, *args, **kwargs):
        import logging
        self.logger = logging.getLogger("ecowitt-test")
        self.logger.addHandler(logging.NullHandler())
        self.pluginPrefs = {}

    def sleep(self, _seconds):
        pass

    class StopThread(Exception):
        pass


_ind.PluginBase = _PluginBase
_ind.Dict = dict
_ind.List = list
_ind.devices = MagicMock()
_ind.devices.folders = []
_ind.variables = MagicMock()
_ind.server = MagicMock()
_ind.kStateImageSel = MagicMock()
sys.modules["indigo"] = _ind

import plugin  # noqa: E402


# ==========================================================================
# UNIT CONVERSIONS  (all return strings)
# ==========================================================================
class TestConvertTemperature:
    def test_freezing(self):
        assert plugin.convert_temperature(32, "C") == "0.0"

    def test_boiling(self):
        assert plugin.convert_temperature(212, "C") == "100.0"

    def test_room(self):
        assert plugin.convert_temperature(68, "C") == "20.0"

    def test_fahrenheit_passthrough(self):
        assert plugin.convert_temperature(50, "F") == "50.0"

    def test_bad_input_returns_zero(self):
        assert plugin.convert_temperature("abc", "C") == "0.0"


class TestConvertWindSpeed:
    def test_kmh(self):
        assert plugin.convert_wind_speed(10, "kmh") == "16.1"

    def test_ms(self):
        assert plugin.convert_wind_speed(10, "ms") == "4.5"

    def test_kts(self):
        assert plugin.convert_wind_speed(10, "kts") == "8.7"

    def test_mph_passthrough(self):
        assert plugin.convert_wind_speed(10, "mph") == "10.0"

    def test_bad_input_returns_zero(self):
        assert plugin.convert_wind_speed("gusty", "kmh") == "0.0"


class TestConvertPressure:
    def test_hpa(self):
        assert plugin.convert_pressure(29.92, "hPa") == "1013.2"

    def test_mmhg(self):
        assert plugin.convert_pressure(30, "mmHg") == "762.0"

    def test_inhg_passthrough(self):
        assert plugin.convert_pressure(29.92, "inHg") == "29.9"

    def test_bad_input_returns_zero(self):
        assert plugin.convert_pressure("", "hPa") == "0.0"


class TestConvertRain:
    def test_mm(self):
        assert plugin.convert_rain(1, "mm") == "25.4"

    def test_inches_passthrough(self):
        assert plugin.convert_rain(1, "in") == "1.0"

    def test_bad_input_returns_zero(self):
        assert plugin.convert_rain(None, "mm") == "0.0"


class TestConvertDistance:
    def test_miles(self):
        assert plugin.convert_distance(10, "mi") == "6.2"

    def test_km_passthrough(self):
        assert plugin.convert_distance(10, "km") == "10.0"

    def test_bad_input_returns_zero(self):
        assert plugin.convert_distance("x", "mi") == "0.0"


# ==========================================================================
# HEAT INDEX  (NWS Rothfusz — returns float degF, or None on bad input)
# ==========================================================================
class TestHeatIndex:
    def test_published_nws_value(self):
        # NWS reference: 90 degF / 70% RH ~ 105.9 degF
        assert abs(plugin.calculate_heat_index(90, 70) - 105.9) < 0.5

    def test_low_humidity_branch(self):
        # rh < 13 and hot triggers the low-humidity correction; must stay sane
        hi = plugin.calculate_heat_index(100, 10)
        assert 90.0 < hi < 120.0

    def test_high_humidity_branch(self):
        # rh > 85 and 80-87 degF triggers the high-humidity correction
        hi = plugin.calculate_heat_index(85, 90)
        assert hi > 85.0

    def test_bad_input_returns_none(self):
        assert plugin.calculate_heat_index("x", 50) is None


# ==========================================================================
# WIND CHILL  (defined only above 3 mph)
# ==========================================================================
class TestWindChill:
    def test_calm_returns_air_temp(self):
        assert plugin.calculate_wind_chill(30, 2) == 30

    def test_windy_below_air_temp(self):
        wc = plugin.calculate_wind_chill(30, 20)
        assert wc < 30

    def test_bad_input_returns_none(self):
        assert plugin.calculate_wind_chill(30, "breezy") is None


# ==========================================================================
# BATTERY DECODING  (three encodings, chosen by field name)
# ==========================================================================
class TestBatteryToPercent:
    def test_level_dead_is_zero_not_full(self):
        # THE headline bug: a 0-5 level sensor at raw 0 is DEAD, not "OK".
        assert plugin.battery_to_percent(0, "pm25batt1") == 0
        assert plugin.battery_to_percent(0, "leakbatt1") == 0
        assert plugin.battery_to_percent(0, "wh57batt") == 0

    def test_level_full(self):
        assert plugin.battery_to_percent(5, "pm25batt1") == 100

    def test_level_midpoints(self):
        assert plugin.battery_to_percent(1, "wh57batt") == 20
        assert plugin.battery_to_percent(3, "leakbatt1") == 60

    def test_binary_ok_is_full(self):
        assert plugin.battery_to_percent(0, "wh65batt") == 100

    def test_binary_low_is_zero(self):
        assert plugin.battery_to_percent(1, "wh65batt") == 0

    def test_single_cell_voltage_ramp(self):
        assert plugin.battery_to_percent(1.2, "soilbatt1") == 0
        assert plugin.battery_to_percent(1.4, "soilbatt1") == 50
        assert plugin.battery_to_percent(1.6, "soilbatt1") == 100

    def test_single_cell_voltage_clamps(self):
        assert plugin.battery_to_percent(2.0, "soilbatt1") == 100
        assert plugin.battery_to_percent(1.1, "soilbatt1") == 0

    def test_high_voltage_array_sensor(self):
        assert plugin.battery_to_percent(2.3, "ws90batt") == 0
        assert plugin.battery_to_percent(2.8, "ws90batt") == 50
        assert plugin.battery_to_percent(3.3, "ws90batt") == 100

    def test_no_field_name_legacy_guess(self):
        # Backward-compatible: no name -> binary/single-cell-voltage guess.
        assert plugin.battery_to_percent(0) == 100
        assert plugin.battery_to_percent(1.4) == 50

    def test_bad_input_returns_zero(self):
        assert plugin.battery_to_percent("x", "pm25batt1") == 0
        assert plugin.battery_to_percent(None, "soilbatt1") == 0


# ==========================================================================
# LDS WATER-LEVEL MATHS
# ==========================================================================
class TestLdsPercent:
    def test_partial_fill(self):
        assert plugin.lds_percent(200, 1000) == 80.0

    def test_empty_when_distance_exceeds_tank(self):
        assert plugin.lds_percent(1200, 1000) == 0.0

    def test_full_when_distance_zero(self):
        assert plugin.lds_percent(0, 1000) == 100.0

    def test_zero_tank_height_no_div_by_zero(self):
        assert plugin.lds_percent(500, 0) == 0.0

    def test_bad_input_returns_zero(self):
        assert plugin.lds_percent("x", 1000) == 0.0


# ==========================================================================
# CONFIG-COERCION GUARDS  (blank/garbage textfield must not crash __init__)
# ==========================================================================
def _make_plugin(prefs):
    p = plugin.Plugin.__new__(plugin.Plugin)
    p.__init__("com.clives.indigoplugin.ecowitt", "Ecowitt", "2.3.0", prefs)
    return p


class TestConfigCoercionGuards:
    @pytest.mark.parametrize("bad", ["", "abc", None])
    def test_blank_or_garbage_does_not_crash(self, bad):
        prefs = {
            "httpPort": bad,
            "dataStaleTimeout": bad,
            "batteryLowThreshold": bad,
            "updateInterval": bad,
            "ldsTankHeight": bad,
        }
        p = _make_plugin(prefs)  # must not raise
        assert p.http_port == plugin.HTTP_PORT
        assert p.stale_timeout == 300
        assert p.battery_threshold == 20
        assert p.update_interval == 30
        assert p.lds_tank_height == 1000

    def test_valid_values_are_honoured(self):
        prefs = {
            "httpPort": "9000",
            "dataStaleTimeout": "120",
            "batteryLowThreshold": "15",
            "updateInterval": "60",
            "ldsTankHeight": "1500",
        }
        p = _make_plugin(prefs)
        assert p.http_port == 9000
        assert p.stale_timeout == 120
        assert p.battery_threshold == 15
        assert p.update_interval == 60
        assert p.lds_tank_height == 1500


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
