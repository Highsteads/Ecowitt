#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# Filename:    test_device_lookup.py
# Description: Contract test for get_or_create_device — a device must be found
#              by its ADDRESS, so renaming it in Indigo does not orphan it and
#              silently create a duplicate on the next payload.
# Author:      CliveS & Claude Opus 5
# Date:        13-09-2026
# Version:     1.0
#
# Runs with no Indigo and no hardware.
#
#   python3 -m pytest tests/ -q        (or: python3 tests/test_device_lookup.py)

import os
import sys
import types
import unittest

PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Ecowitt.indigoPlugin", "Contents", "Server Plugin",
                      "plugin.py")


class FakeDev:
    def __init__(self, did, name, device_type, address=""):
        self.id = did
        self.name = name
        self.deviceTypeId = device_type
        self.address = address
        self.pluginProps = {}
        self.replaced = []

    def replacePluginPropsOnServer(self, props):
        self.pluginProps = dict(props)
        self.replaced.append(dict(props))
        # Indigo reflects a plugin prop literally named `address` into the
        # device's native address field. Measured live 13-09-2026: the native
        # attribute itself is read-only once the device exists, so this is the
        # only writable route and the fake must model it or the backfill test
        # would pass against code that cannot actually work.
        if "address" in props:
            self.address = props["address"]

    def replaceOnServer(self):
        raise RuntimeError('the attribute "address" is read-only on this instance')


class FakeDevices(dict):
    def iter(self, filt):
        want = filt.split(".", 1)[1] if "." in filt else filt
        return [d for d in self.values() if d.deviceTypeId == want]


def load_plugin_class():
    """Exec the whole of plugin.py with indigo stubbed, return (module, stub)."""
    src = open(PLUGIN, encoding="utf-8").read()
    devices = FakeDevices()
    created = []

    def _create(protocol=None, address="", name="", description="",
                pluginId="", deviceTypeId="", folder=None):
        did = 9000 + len(created)
        d = FakeDev(did, name, deviceTypeId, address)
        devices[did] = d
        created.append(d)
        return d

    stub = types.SimpleNamespace(
        PluginBase=object, Dict=dict, List=list,
        devices=devices, variables={},
        kProtocol=types.SimpleNamespace(Plugin="plugin"),
        device=types.SimpleNamespace(create=_create),
        server=types.SimpleNamespace(log=lambda *a, **k: None,
                                     getInstallFolderPath=lambda: "/tmp"),
    )
    stub.created = created
    sys.modules["indigo"] = stub
    mod = types.ModuleType("ecowitt_plugin")
    mod.__dict__["indigo"] = stub
    exec(compile(src, PLUGIN, "exec"), mod.__dict__)
    return mod, stub


MOD, STUB = load_plugin_class()


def fresh_plugin():
    """A Plugin with only the attributes get_or_create_device touches."""
    STUB.devices.clear()
    del STUB.created[:]
    p = MOD.Plugin.__new__(MOD.Plugin)
    p.device_list = {}
    p.auto_create = True
    p.device_prefix = ""
    p.include_station_id = False
    p.device_folder = 0
    p.pluginId = "com.clives.indigoplugin.ecowitt"
    p.debug = False
    return p


TYPE = "ecowittMultiChannel"


class TestFoundByName(unittest.TestCase):
    """The legacy path must keep working — devices that predate addressing."""

    def test_existing_device_with_matching_name_is_reused(self):
        p = fresh_plugin()
        existing = FakeDev(1, "Multi-Channel 3", TYPE, "")
        STUB.devices[1] = existing
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertIs(got, existing)
        self.assertEqual(len(STUB.created), 0, "must not create a duplicate")


class TestFoundByAddress(unittest.TestCase):
    """The point of the whole exercise: a rename must not orphan the device."""

    def test_a_renamed_device_is_still_found(self):
        p = fresh_plugin()
        renamed = FakeDev(1, "Dining Room Temperature", TYPE, "multichannel_3")
        STUB.devices[1] = renamed
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertIs(got, renamed,
                      "renaming the device in Indigo orphaned it")

    def test_a_renamed_device_does_not_spawn_a_duplicate(self):
        p = fresh_plugin()
        STUB.devices[1] = FakeDev(1, "Dining Room Temperature", TYPE, "multichannel_3")
        p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertEqual(len(STUB.created), 0,
                         "a rename created a second device for the same channel")

    def test_address_wins_over_a_name_collision(self):
        # Two devices, one with the right address under a new name and one with
        # the old name but the WRONG address. The address must decide.
        p = fresh_plugin()
        right = FakeDev(1, "Dining Room Temperature", TYPE, "multichannel_3")
        wrong = FakeDev(2, "Multi-Channel 3", TYPE, "multichannel_7")
        STUB.devices[1] = right
        STUB.devices[2] = wrong
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertIs(got, right)


class TestAddressBackfill(unittest.TestCase):
    """Legacy devices carry a blank address — fix them on the way past."""

    def test_a_legacy_device_found_by_name_gets_its_address_filled_in(self):
        p = fresh_plugin()
        legacy = FakeDev(1, "Multi-Channel 3", TYPE, "")
        STUB.devices[1] = legacy
        p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertEqual(legacy.address, "multichannel_3")

    def test_backfilled_device_survives_a_later_rename(self):
        p = fresh_plugin()
        legacy = FakeDev(1, "Multi-Channel 3", TYPE, "")
        STUB.devices[1] = legacy
        p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        # user renames it, and the cache is lost on the next plugin restart
        legacy.name = "Dining Room Temperature"
        p.device_list = {}
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertIs(got, legacy)
        self.assertEqual(len(STUB.created), 0)

    def test_an_existing_address_is_never_overwritten(self):
        p = fresh_plugin()
        dev = FakeDev(1, "Multi-Channel 3", TYPE, "something_else")
        STUB.devices[1] = dev
        p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertEqual(dev.address, "something_else")

    def test_a_failing_backfill_still_returns_the_device(self):
        # The tidy-up must never be able to break the update path.
        p = fresh_plugin()
        legacy = FakeDev(1, "Multi-Channel 3", TYPE, "")
        def boom(_props): raise RuntimeError("server said no")
        legacy.replacePluginPropsOnServer = boom
        STUB.devices[1] = legacy
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertIs(got, legacy)


class TestBackfillUsesTheWritableRoute(unittest.TestCase):
    """`dev.address = ...` is read-only on an existing device — proven live."""

    def test_the_read_only_attribute_route_is_not_used(self):
        p = fresh_plugin()
        legacy = FakeDev(1, "Multi-Channel 3", TYPE, "")
        STUB.devices[1] = legacy          # its replaceOnServer raises, as Indigo does
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertIs(got, legacy)
        self.assertEqual(legacy.address, "multichannel_3",
                         "backfill must go through the plugin props")

    def test_existing_props_are_preserved_not_replaced(self):
        # replacePluginPropsOnServer REPLACES the dict, so the merge matters.
        p = fresh_plugin()
        legacy = FakeDev(1, "Multi-Channel 3", TYPE, "")
        legacy.pluginProps = {"keepMe": "yes"}
        STUB.devices[1] = legacy
        p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertEqual(legacy.pluginProps.get("keepMe"), "yes")
        self.assertEqual(legacy.pluginProps.get("address"), "multichannel_3")


class TestCreation(unittest.TestCase):
    def test_a_genuinely_new_channel_is_created_with_its_address(self):
        p = fresh_plugin()
        got = p.get_or_create_device("Multi-Channel 5", TYPE, "multichannel_5")
        self.assertIsNotNone(got)
        self.assertEqual(got.address, "multichannel_5")
        self.assertEqual(len(STUB.created), 1)

    def test_auto_create_disabled_creates_nothing(self):
        p = fresh_plugin()
        p.auto_create = False
        self.assertIsNone(p.get_or_create_device("Multi-Channel 5", TYPE, "multichannel_5"))
        self.assertEqual(len(STUB.created), 0)

    def test_the_cache_returns_the_same_device(self):
        p = fresh_plugin()
        first = p.get_or_create_device("Multi-Channel 5", TYPE, "multichannel_5")
        second = p.get_or_create_device("Multi-Channel 5", TYPE, "multichannel_5")
        self.assertIs(first, second)
        self.assertEqual(len(STUB.created), 1)

    def test_a_device_of_another_type_is_never_matched(self):
        p = fresh_plugin()
        STUB.devices[1] = FakeDev(1, "Multi-Channel 3", "ecowittSoil", "multichannel_3")
        got = p.get_or_create_device("Multi-Channel 3", TYPE, "multichannel_3")
        self.assertEqual(got.deviceTypeId, TYPE)
        self.assertEqual(len(STUB.created), 1, "should have created the right type")


if __name__ == "__main__":
    unittest.main(verbosity=2)
