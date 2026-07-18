# Ecowitt Weather Station

**Indigo home automation plugin.**

Indigo plugin for Ecowitt weather stations — discovers indoor/outdoor sensors, multi-channel temperature/humidity, wind, rain and solar/UV sensors automatically and exposes live data as native Indigo devices. Computes useful extras with no extra hardware: dew point, VPD, wind chill, feels-like (apparent temperature) and heat index.

**Author:** CliveS & Claude
**Platform:** Indigo 2022.1 or later, macOS (Python 3.10+ bundled with Indigo)

*Developed and tested on Indigo 2025.2 / Python 3.13. Older Indigo releases that meet the minimum API version above should also work — the API floor is what Indigo's plugin loader actually checks.*
**Bundle ID:** `com.clives.indigoplugin.ecowitt`
**Version:** 2.4.0

---

## Installation

1. Go to the [Releases page](https://github.com/Highsteads/Ecowitt/releases) and download `Ecowitt.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `Ecowitt.indigoPlugin`
3. Double-click `Ecowitt.indigoPlugin` — Indigo will install it automatically
4. In Indigo: **Plugins → Manage Plugins → Enable** Ecowitt Weather Station
5. Open **Plugins → Ecowitt Weather Station → Configure** and fill in any required fields

---

## Credentials — `IndigoSecrets.py` vs `IndigoSecrets_example.py`

This plugin (along with all CliveS Indigo plugins) reads sensitive values from
a shared master credentials file at:

`/Library/Application Support/Perceptive Automation/IndigoSecrets.py`

| File | Purpose | Real data? | Committed to GitHub? |
|------|---------|------------|----------------------|
| `IndigoSecrets.py` | Working file the plugin reads at runtime. Keep a backup in a password manager. | YES | **NO** — listed in `.gitignore` |
| `IndigoSecrets_example.py` | Template only — empty placeholders. Shipped in the plugin bundle. | NO | YES |

If you do not have `IndigoSecrets.py`, copy `IndigoSecrets_example.py` from
the plugin bundle to `/Library/Application Support/Perceptive Automation/` and rename it to `IndigoSecrets.py`, then fill in your values. Or skip
`IndigoSecrets.py` entirely and enter values via the plugin's configuration
dialog — `IndigoSecrets.py` wins over the dialog when both are set.

If a required value is set in NEITHER source the plugin logs an ERROR
pointing the user to either fill in the matching field or add the key to
`IndigoSecrets.py`.

---

## Logging

Every log line is prefixed with a millisecond timestamp `[HH:MM:SS.mmm]` so
events can be correlated tightly with other CliveS plugins (Device Activity
Monitor uses the same convention).

To turn the prefix off (or back on) at any time:

**Plugins → Ecowitt Weather Station → Toggle Timestamps in Log (on/off)**

The setting is stored in `pluginPrefs` (`enableTimestampLogging`) and persists
across restarts. Defaults to ON.

---

## Recent changes

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
