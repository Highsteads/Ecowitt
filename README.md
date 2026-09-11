# Ecowitt Weather Station

**Indigo home automation plugin.**

Indigo plugin for Ecowitt weather stations — discovers indoor/outdoor sensors, multi-channel temperature/humidity, wind, rain and solar/UV sensors automatically and exposes live data as native Indigo devices. Computes useful extras with no extra hardware: dew point, VPD, wind chill, feels-like (apparent temperature) and heat index.

**Author:** CliveS & Claude
**Platform:** Indigo 2022.1 or later, macOS (Python 3.10+ bundled with Indigo)

*Developed and tested on Indigo 2025.2 / Python 3.13. Older Indigo releases that meet the minimum API version above should also work — the API floor is what Indigo's plugin loader actually checks.*
**Bundle ID:** `com.clives.indigoplugin.ecowitt`
**Version:** 2.5.2

---

## Installation

1. Go to the [Releases page](https://github.com/Highsteads/Ecowitt/releases) and download `Ecowitt.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `Ecowitt.indigoPlugin`
3. Double-click `Ecowitt.indigoPlugin` — Indigo will install it automatically
4. In Indigo: **Plugins → Manage Plugins → Enable** Ecowitt Weather Station
5. Open **Plugins → Ecowitt Weather Station → Configure** and fill in any required fields

---

## Device types

The plugin creates devices from what the station actually uploads, so you do not
pick a type by hand. Fifteen types are defined:

| Device | What it reports |
|---|---|
| Ecowitt Main Gateway | Station model, frequency, uptime, upload interval, and connection status (Live / Stale / Offline) |
| Ecowitt Outdoor Sensor | Temperature and humidity, plus the computed dew point, VPD, feels-like and heat index |
| Ecowitt Indoor Sensor | Indoor temperature and humidity, absolute and relative pressure |
| Ecowitt Wind Sensor | Speed, gust, highest gust of the day, direction in degrees and as a compass point, plus the computed wind chill |
| Ecowitt Rain Sensor | Rain rate, and event, hourly, daily, weekly, monthly, yearly and total rainfall |
| Ecowitt Solar/UV Sensor | Solar radiation and UV index |
| Ecowitt Multi-Channel Sensor | One device per channel — temperature and humidity |
| Ecowitt Soil Sensor | Soil moisture, one device per channel |
| Ecowitt PM2.5 Sensor | PM2.5, its 24-hour average, PM10 and CO2 |
| Ecowitt Lightning Sensor | Strike count, distance to the last strike, and when it struck |
| Ecowitt Leak Sensor | Wet or dry, one device per channel |
| Ecowitt Water Level Sensor | Measured distance, water level in mm, and level as a percentage of tank height |
| Ecowitt WH46 Air Quality | PM1, PM2.5, PM4, PM10, CO2, temperature and humidity |
| Ecowitt WH52 Soil Sensor | Soil moisture, temperature and electrical conductivity |
| Ecowitt WN38 WBGT Sensor | Black globe temperature and wet-bulb globe temperature |

Dew point, VPD, feels-like, heat index and wind chill are worked out by the plugin
from the readings the station already sends, so they need no extra hardware.

Every device carries `lastUpdate` and `deviceOnline`. Sensors that run on a battery
also carry a `battery` percentage, and most of those add a `batteryLow` flag.

---

## Credentials — `IndigoSecrets.py` vs `IndigoSecrets_example.py`

This plugin, like every CliveS Indigo plugin, reads sensitive values from one
shared master file:

`/Library/Application Support/Perceptive Automation/IndigoSecrets.py`

| File | Purpose | Real data? | Committed to GitHub? |
|------|---------|------------|----------------------|
| `IndigoSecrets.py` | Working file the plugin reads at runtime. Keep a backup in a password manager. | YES | **NO** — listed in `.gitignore` |
| `IndigoSecrets_example.py` | Template only — empty placeholders. Shipped in the plugin bundle. | NO | YES |

If you don't have `IndigoSecrets.py`, copy `IndigoSecrets_example.py` out of
the plugin bundle into `/Library/Application Support/Perceptive Automation/`,
rename it to `IndigoSecrets.py`, and fill in your values. Or skip the file
altogether and type the values into the plugin's configuration dialog — where
both are set, `IndigoSecrets.py` wins.

If neither source supplies a value the plugin needs, it logs an ERROR naming
the key and telling you to either fill in the matching field or add the key to
`IndigoSecrets.py`.

---

## Logging

Every log line carries a millisecond timestamp `[HH:MM:SS.mmm]`, so you can
line events up precisely against the other CliveS plugins — Device Activity
Monitor uses the same format.

To turn the prefix off, or back on, at any time:

**Plugins → Ecowitt Weather Station → Toggle Timestamps in Log (on/off)**

The plugin stores the setting in `pluginPrefs` (`enableTimestampLogging`) and
it survives a restart. It defaults to ON.

---

## Recent changes


**v2.5.2** - **The plugin's About item pointed at a repository that does not exist.** Indigo builds the *About Ecowitt* menu item from the support address in the plugin bundle, and that address named a repository called EcowittWeather, which is not there. It now opens github.com/Highsteads/Ecowitt, where the releases and the issue tracker are. The bundle's GitHub owner and repository record carried the same wrong name and is corrected too. Nothing else changed.

**v2.5.1** - **The settings dialog was stretched wider than its own window, so the help text beside each setting was cut off mid-sentence.** The short help that can be attached to a setting is drawn on a single line and never wraps, so the longest one decides how wide every row is — and the window cannot be widened past a fixed maximum. All eight long ones have moved into ordinary description paragraphs, which do wrap. Two new checks fail the build if any help text or setting label grows long enough to do it again. No setting or behaviour changed.
**v2.5.0** — the outdoor dew point is a real reading at last. It had always been published from a field the station never sends, so the state sat at 0.0 °C — which looks like a measurement rather than a gap, and had gone unnoticed for that reason. It is now worked out from the temperature and humidity the station does send, to about a third of a degree, and it reports nothing at all when the inputs cannot support an answer. A station that does send its own dew point still wins.

**v2.4.2** — shared-utility refresh. Calling the log timestamp filter twice no longer double-stamps every line, a log call with mismatched placeholders keeps its arguments instead of dropping them, and the module now imports cleanly outside Indigo so the offline tests can exercise it.

**v2.4.1** — log-level fix. Warnings and errors raised through the plugin's own log helper had been coming out as ordinary info lines, because Indigo wants a real logging level rather than the name of one and quietly ignores the name. The amber and red entries people rely on for diagnosis now show up as intended.

**v2.4.0** — improvements building on the v2.3.0 fixes (test suite now 65 tests).

- Low-battery alerts work properly for a battery that goes flat more than once. The alert now re-arms when a battery is replaced, so the next time it runs down you are told again — previously a second low was only noticed after a plugin restart.
- One misbehaving sensor channel can no longer stop the other channels in the same group from updating.
- The Main Gateway now shows an "Offline" connection status when the station has genuinely stopped reporting, in addition to the existing Live and Stale states.
- If the plugin can't start its receiver (for example the port is already in use) it now honestly reports the server as stopped instead of claiming it is running.
- **Show Plugin Info** now prints the exact address to point your weather station at — handy when setting up or asking for help.

**v2.3.0** — a round of reliability fixes, plus the plugin's first test suite (46 tests).

- Blank or cleared numeric settings no longer stop the plugin from loading. If a field like the HTTP port, stale-data timeout or low-battery threshold was ever left empty, the plugin now quietly falls back to its default instead of failing to start.
- Battery reporting is much more accurate. Ecowitt sends battery readings in three different ways depending on the sensor, and the plugin now recognises each one properly. In particular, a flat battery on a PM2.5, leak or lightning sensor used to show as 100% full and never raise a low-battery warning — that is now reported correctly, so those alerts actually fire.
- Readings from the gateway are read in full even when the network splits the message across packets, so no fields get dropped.
- One misbehaving sensor in an upload can no longer stop the others in the same upload from updating. Soil and WH52 sensors now support up to 16 channels.
- The low-battery threshold is now a straightforward percentage (0-100, default 20), and works consistently across every sensor type.

---

## Repository structure

```
README.md                        ← this file (GitHub displays this)
Ecowitt.indigoPlugin/
├── Contents/
│   ├── Info.plist
│   └── Server Plugin/
│       ├── plugin.py
│       └── ...
└── Contents/Server Plugin/IndigoSecrets_example.py   ← credential template
```

## Authors & licence

Vibed into existence by **CliveS**, who knew what he wanted, argued until he got it, and tested it on a real house. Typed at inhuman speed by **Claude** (Anthropic), who mostly did as it was told.

© 2026 CliveS · [MIT licence](LICENSE) — copy it, fork it, bend it, break it, fix it, ship it. If it breaks, you get to keep both pieces.
