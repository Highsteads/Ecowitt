#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# Filename:    test_gateway_time.py
# Description: Contract test for gateway_local_time — the Main Gateway's
#              lastUpdate, which was showing a URL-encoded UTC string while
#              every other device showed local time.
# Author:      CliveS & Claude Opus 5
# Date:        13-09-2026
# Version:     1.0
#
#   python3 -m pytest tests/ -q        (or: python3 tests/test_gateway_time.py)

import os
import sys
import time
import types
import unittest

# Pin the zone BEFORE the module is imported, so the result does not depend on
# the host running the suite. The bug is a timezone bug — a test that inherits
# whatever zone the machine happens to be in cannot be trusted to prove it.
os.environ["TZ"] = "Europe/London"
time.tzset()

PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Ecowitt.indigoPlugin", "Contents", "Server Plugin",
                      "plugin.py")


def load_helpers():
    src = open(PLUGIN, encoding="utf-8").read()
    head = src.split("class Plugin", 1)[0]
    stub = types.SimpleNamespace(
        PluginBase=object, Dict=dict, List=list, devices={}, variables={},
        server=types.SimpleNamespace(log=lambda *a, **k: None,
                                     getInstallFolderPath=lambda: "/tmp"))
    sys.modules["indigo"] = stub
    mod = types.ModuleType("ecowitt_helpers_time")
    mod.__dict__["indigo"] = stub
    exec(compile(head, PLUGIN, "exec"), mod.__dict__)
    return mod


gateway_local_time = load_helpers().gateway_local_time
FALLBACK = "FELL-BACK"


class TestSummerAndWinter(unittest.TestCase):
    """Both seasons, because a UTC bug is invisible for four months of the year."""

    def test_bst_the_real_live_value(self):
        # Exactly what the gateway sent on 13-09-2026 while its five siblings
        # all read 09:04:35.
        self.assertEqual(gateway_local_time("2026-09-13+08:04:35", FALLBACK),
                         "2026-09-13 09:04:35")

    def test_gmt_is_left_alone(self):
        self.assertEqual(gateway_local_time("2026-01-15+08:04:35", FALLBACK),
                         "2026-01-15 08:04:35")

    def test_the_plus_is_decoded_not_printed(self):
        self.assertNotIn("+", gateway_local_time("2026-09-13+08:04:35", FALLBACK))

    def test_an_already_spaced_value_works_too(self):
        self.assertEqual(gateway_local_time("2026-09-13 08:04:35", FALLBACK),
                         "2026-09-13 09:04:35")


class TestUnusableInput(unittest.TestCase):
    """A timestamp we cannot read is no reason to show nothing."""

    def test_missing_returns_the_fallback(self):
        for bad in (None, "", 0):
            self.assertEqual(gateway_local_time(bad, FALLBACK), FALLBACK)

    def test_unparseable_returns_the_fallback(self):
        for bad in ("not a date", "2026-13-45+99:99:99", "2026-09-13", "{}"):
            self.assertEqual(gateway_local_time(bad, FALLBACK), FALLBACK,
                             f"{bad!r} should have fallen back")

    def test_a_non_string_does_not_raise(self):
        self.assertEqual(gateway_local_time({"a": 1}, FALLBACK), FALLBACK)


class TestShape(unittest.TestCase):
    def test_output_matches_the_format_every_other_device_uses(self):
        out = gateway_local_time("2026-09-13+08:04:35", FALLBACK)
        # same strftime the five sibling devices use: '%Y-%m-%d %H:%M:%S'
        import datetime as dt
        dt.datetime.strptime(out, "%Y-%m-%d %H:%M:%S")   # raises if it drifted

    def test_the_dst_boundary_hour_is_handled(self):
        # 00:30 UTC on the day the UK springs forward is still GMT.
        self.assertEqual(gateway_local_time("2026-03-29+00:30:00", FALLBACK),
                         "2026-03-29 00:30:00")
        # 01:30 UTC that same day is BST.
        self.assertEqual(gateway_local_time("2026-03-29+01:30:00", FALLBACK),
                         "2026-03-29 02:30:00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
