#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# Filename:    test_dew_point.py
# Description: Contract test for calculate_dew_point_c — the computed dew point
#              that replaced a state which had never been populated.
# Author:      CliveS & Claude Opus 5
# Date:        17-08-2026
# Version:     1.0
#
# Runs with no Indigo and no hardware: the module-level half of plugin.py is
# exec'd on its own with `indigo` stubbed, which is all a pure helper needs.
#
#   python3 -m pytest tests/ -q        (or: python3 tests/test_dew_point.py)

import math
import os
import sys
import types
import unittest

PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Ecowitt.indigoPlugin", "Contents", "Server Plugin",
                      "plugin.py")


def load_helpers():
    """Exec everything above `class Plugin` with indigo stubbed out."""
    src = open(PLUGIN, encoding="utf-8").read()
    head = src.split("class Plugin", 1)[0]
    stub = types.SimpleNamespace(
        PluginBase=object, Dict=dict, List=list, devices={}, variables={},
        server=types.SimpleNamespace(log=lambda *a, **k: None,
                                     getInstallFolderPath=lambda: "/tmp"))
    sys.modules["indigo"] = stub
    mod = types.ModuleType("ecowitt_helpers")
    mod.__dict__["indigo"] = stub
    exec(compile(head, PLUGIN, "exec"), mod.__dict__)
    return mod


HELPERS = load_helpers()
dew_point_c = HELPERS.calculate_dew_point_c


class TestDewPoint(unittest.TestCase):

    def test_known_values(self):
        """Magnus/Sonntag against hand-worked figures, within 0.15 degC."""
        for temp_c, rh, expected in [
            (13.2, 91, 11.76),      # the live reading that exposed the bug
            (14.5, 75, 10.12),      # the 6 August capture
            (25.0, 50, 13.85),
            (30.0, 90, 28.19),
            (-5.0, 80, -7.92),
        ]:
            got = dew_point_c(temp_c, rh)
            self.assertIsNotNone(got, f"{temp_c}C {rh}% returned None")
            self.assertAlmostEqual(got, expected, delta=0.15,
                                   msg=f"{temp_c}C {rh}%")

    def test_saturated_air_equals_air_temperature(self):
        """At 100% humidity the dew point IS the air temperature."""
        for temp_c in (-10.0, 0.0, 13.2, 25.0):
            self.assertAlmostEqual(dew_point_c(temp_c, 100), temp_c, delta=0.01)

    def test_never_above_air_temperature(self):
        """Physically impossible, and the tell that the formula is inverted."""
        for temp_c in range(-20, 45, 5):
            for rh in range(1, 101, 7):
                got = dew_point_c(float(temp_c), float(rh))
                self.assertIsNotNone(got)
                self.assertLessEqual(got, temp_c + 0.01,
                                     f"dew point above air temp at "
                                     f"{temp_c}C {rh}%")

    def test_falls_as_humidity_falls(self):
        """Monotonic in humidity at a fixed temperature."""
        previous = None
        for rh in range(100, 4, -5):
            got = dew_point_c(15.0, float(rh))
            if previous is not None:
                self.assertLess(got, previous, f"not falling at {rh}%")
            previous = got

    def test_unusable_input_returns_none(self):
        """None, never a number — a bad reading must not look like a measurement.

        This is the whole point of the exercise: the state it replaces sat at
        0.0 because a freshly created Number state is born there, and 0.0 read
        as a plausible winter dew point rather than as missing data.
        """
        for temp_c, rh in [
            (13.2, 0),          # no dew point exists; log(0) is not a number
            (13.2, -1),
            (13.2, 101),
            (13.2, None),
            (13.2, ""),
            (None, 50),
            ("warm", 50),
            (13.2, "damp"),
        ]:
            self.assertIsNone(dew_point_c(temp_c, rh),
                              f"expected None for T={temp_c!r} RH={rh!r}")

    def test_result_is_finite(self):
        """No NaN or infinity reaches a device state."""
        for temp_c in (-40.0, 0.0, 50.0):
            for rh in (1.0, 50.0, 100.0):
                got = dew_point_c(temp_c, rh)
                self.assertTrue(math.isfinite(got), f"{temp_c}C {rh}%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
