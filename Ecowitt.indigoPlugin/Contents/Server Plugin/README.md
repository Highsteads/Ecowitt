# Ecowitt Weather Station Plugin for Indigo

**Version:** 1.0  
**Author:** CliveS & Claude 4  
**Date:** 2025-10-29

## Overview

This Indigo plugin allows you to receive comprehensive weather data from Ecowitt weather stations (and compatible devices like Ambient Weather, Froggit, etc.) directly into your Indigo home automation system.

The plugin uses the **Custom Server Upload** method, where your Ecowitt gateway pushes data via HTTP to a local server running within Indigo. This approach provides:
- Complete sensor data access
- No reliance on cloud services
- Fast updates (16-60 second intervals)
- Automatic device creation
- Battery status monitoring

## Supported Sensors

The plugin automatically creates devices for all detected sensors:

### Core Sensors
- **Main Gateway** - Station information, model, firmware
- **Outdoor Sensor (WH32, WH25, WH26, WH65)** - Temperature, humidity, dew point
- **Indoor Sensor (Gateway built-in)** - Temperature, humidity, barometric pressure
- **Wind Sensor (WH68, WS80, WS90)** - Speed, direction, gust, wind chill
- **Rain Sensor (WH40, WH80, WS90)** - Rate, hourly, daily, weekly, monthly, yearly totals
- **Solar/UV Sensor** - Solar radiation, UV index

### Additional Sensors
- **Multi-Channel Temp/Humidity (WH31)** - Up to 8 channels
- **Soil Moisture (WH51)** - Up to 8 sensors
- **PM2.5 Air Quality (WH41, WH43, WH45)** - Up to 4 sensors, plus CO2
- **Lightning Detector (WH57)** - Strike count, distance, last strike time
- **Water Leak Detectors (WH55)** - Up to 4 sensors

## Installation

### 1. Plugin Installation

1. Copy these files to your Indigo plugin folder:
   ```
   ~/Documents/Indigo/Plugins/Ecowitt.indigoPlugin/Contents/Server Plugin/
   ```

2. Required files:
   - `ecowitt_plugin.py` (rename to `plugin.py`)
   - `Devices.xml`
   - `PluginConfig.xml`

3. Create or update `Info.plist` with plugin metadata

4. Reload plugins in Indigo

### 2. Ecowitt Gateway Configuration

#### Using WS View Mobile App:

1. Open the **WS View** app (available for iOS and Android)

2. Select your gateway device from the device list

3. Tap **More** (top right) → **Weather Services**

4. Tap **Next** until you reach the **Customized** section

5. Enable **Customized** upload

6. Configure the following:
   ```
   Protocol Type:    Ecowitt
   Server IP:        [Your Indigo Server IP, e.g., 192.168.1.20]
   Path:             /data/report/
   Port:             8088 (or your configured port)
   Upload Interval:  30 seconds (recommended, range: 16-60)
   ```

7. Save the configuration

#### Using Device Web Interface (if available):

Some gateway models (GW1000, GW1100, GW2000, etc.) have a web interface:

1. Access the gateway at `http://[gateway-ip]`
2. Navigate to **Weather Services** → **Customized**
3. Configure as above

### 3. Verification

1. Check Indigo log for:
   ```
   [HH:MM:SS] HTTP server started on port 8088
   [HH:MM:SS] Configure your Ecowitt device to POST to: http://[YOUR_INDIGO_IP]:8088/data/report/
   ```

2. Within 30-60 seconds, you should see:
   ```
   [HH:MM:SS] Received request from [gateway-ip]
   [HH:MM:SS] Processing weather data: Station=GW1000_V1.6.8
   [HH:MM:SS] Creating new device: Main Gateway
   [HH:MM:SS] Weather data processed successfully
   ```

3. Check Indigo's device list - devices will be created automatically as sensor data arrives

## Plugin Configuration

### Settings (Plugin Preferences)

- **HTTP Server Port** (default: 8088)
  - Port for receiving data from Ecowitt gateway
  - Range: 1024-65535
  - Ensure this port is not blocked by firewall
  - If changed, restart plugin and update gateway configuration

- **Use Metric Units** (default: Yes)
  - Checked: Celsius, km/h, mm, hPa
  - Unchecked: Fahrenheit, mph, inches, inHg

- **Show Debug Information** (default: No)
  - Enable for troubleshooting
  - Shows detailed HTTP requests and data parsing

## Available Data Fields

### Main Gateway Device
- Station Type (e.g., "GW1000_V1.6.8")
- Model (e.g., "GW1000_Pro")
- Frequency (e.g., "915M", "868M", "433M")
- Pass Key (unique device identifier)
- Last Update timestamp
- Runtime
- Update Interval

### Outdoor Sensor
- Temperature (°F or °C)
- Humidity (%)
- Dew Point
- Battery Level

### Indoor Sensor  
- Temperature (°F or °C)
- Humidity (%)
- Absolute Pressure (inHg or hPa)
- Relative Pressure (inHg or hPa)

### Wind Sensor
- Wind Speed (mph or km/h)
- Wind Direction (0-360°)
- Wind Gust (mph or km/h)
- Max Daily Gust
- Wind Chill

### Rain Sensor
- Rain Rate (in/h or mm/h)
- Event Rain
- Hourly Rain
- Daily Rain
- Weekly Rain
- Monthly Rain
- Yearly Rain
- Total Rain

### Solar/UV Sensor
- Solar Radiation (W/m²)
- UV Index (0-15)

### Multi-Channel Sensors (1-8)
- Channel Number
- Temperature
- Humidity
- Battery Level

### Soil Moisture Sensors (1-8)
- Sensor Number
- Moisture (%)
- Battery Level

### PM2.5 Air Quality Sensors (1-4)
- Sensor Number
- PM2.5 (µg/m³)
- PM2.5 24h Average
- PM10 (µg/m³) - WH45 only
- CO2 (ppm) - WH45 only
- Battery Level

### Lightning Sensor
- Strike Count
- Distance (km or miles)
- Last Strike Time
- Battery Level

### Water Leak Sensors (1-4)
- Sensor Number
- Leak Status ("Leak Detected" / "No Leak")
- Battery Level

## Data Format Details

### Ecowitt Protocol Parameters

The gateway sends POST data in URL-encoded format. Here are the main parameters:

#### Station Information
```
PASSKEY          = Device unique identifier
stationtype      = Firmware version
model            = Hardware model
freq             = RF frequency (915M/868M/433M)
dateutc          = UTC timestamp
runtime          = Gateway uptime
interval         = Update interval
```

#### Temperature Parameters
```
tempf            = Outdoor temperature (°F)
tempinf          = Indoor temperature (°F)
temp1f-temp8f    = Multi-channel temperatures (°F)
dewptf           = Dew point (°F)
windchillf       = Wind chill (°F)
```

#### Humidity Parameters
```
humidity         = Outdoor humidity (%)
humidityin       = Indoor humidity (%)
humidity1-8      = Multi-channel humidity (%)
```

#### Pressure Parameters
```
baromrelin       = Relative barometric pressure (inHg)
baromabsin       = Absolute barometric pressure (inHg)
```

#### Wind Parameters
```
winddir          = Wind direction (degrees, 0-360)
windspeedmph     = Wind speed (mph)
windgustmph      = Wind gust (mph)
maxdailygust     = Maximum daily gust (mph)
```

#### Rain Parameters
```
rainratein       = Rain rate (in/h)
eventrainin      = Event rain (in)
hourlyrainin     = Hourly rain (in)
dailyrainin      = Daily rain (in)
weeklyrainin     = Weekly rain (in)
monthlyrainin    = Monthly rain (in)
yearlyrainin     = Yearly rain (in)
totalrainin      = Total rain (in)
```

#### Solar/UV Parameters
```
solarradiation   = Solar radiation (W/m²)
uv               = UV index (0-15)
```

#### Soil Moisture Parameters
```
soilmoisture1-8  = Soil moisture (%)
soilbatt1-8      = Soil sensor battery
```

#### Air Quality Parameters
```
pm25_1-4         = PM2.5 reading (µg/m³)
pm25_24h_1-4     = PM2.5 24h average (µg/m³)
pm25_co2         = PM2.5 from WH45 (µg/m³)
pm10_co2         = PM10 from WH45 (µg/m³)
co2              = CO2 level (ppm)
```

#### Lightning Parameters
```
lightning        = Lightning distance (km)
lightning_num    = Lightning strike count
lightning_time   = Last strike time
```

#### Leak Detection Parameters
```
leak1-4          = Leak status (0=no leak, 1=leak)
leakbatt1-4      = Leak sensor battery
```

#### Battery Parameters
```
wh65batt         = WH65 outdoor sensor battery
wh25batt         = WH25 outdoor sensor battery
wh26batt         = WH26 outdoor sensor battery
wh40batt         = WH40 rain sensor battery
wh80batt         = WH80 wind sensor battery
wh57batt         = WH57 lightning sensor battery
batt1-8          = Multi-channel sensor batteries
soilbatt1-8      = Soil sensor batteries
pm25batt1-4      = PM2.5 sensor batteries
leakbatt1-4      = Leak sensor batteries
```

## Troubleshooting

### No data received

1. **Check network connectivity:**
   - Ensure Ecowitt gateway and Indigo server are on same network
   - Ping Indigo server from another device: `ping 192.168.100.160`

2. **Verify port configuration:**
   - Check plugin preferences for correct port (default: 8088)
   - Ensure port is not blocked by firewall
   - On macOS: System Preferences → Security & Privacy → Firewall

3. **Check gateway configuration:**
   - Verify Server IP matches Indigo server IP
   - Verify Port matches plugin configuration
   - Verify Path is `/data/report/`
   - Protocol must be "Ecowitt" not "Wunderground"

4. **Enable debug logging:**
   - Plugin Preferences → Check "Show Debug Information"
   - Check Indigo log for HTTP requests

### Devices not created automatically

1. **Check incoming data:**
   - Enable debug logging
   - Look for "Processing weather data" messages

2. **Verify sensor detection:**
   - Sensors only create devices when data is present
   - Wait for full update cycle (30-60 seconds)
   - Check sensor batteries (low battery = no data)

### Incorrect values

1. **Check unit settings:**
   - Plugin Preferences → Use Metric Units
   - Changes affect all new readings

2. **Verify sensor calibration:**
   - Use WS View app to calibrate sensors
   - Calibration is done at gateway, not plugin

### HTTP server won't start

1. **Port already in use:**
   - Change port in plugin preferences
   - Common ports to avoid: 80, 443, 8080, 8123

2. **Permission issues:**
   - Ports below 1024 require root access
   - Use ports 1024-65535

## Advanced Configuration

### Multiple Stations

To support multiple Ecowitt stations:

1. Install plugin once
2. Configure each gateway with same Indigo server IP and port
3. Devices are distinguished by:
   - Gateway PASSKEY (stored in Main Gateway device)
   - Device addresses include station identifier

### Custom Port Forwarding

To receive data from remote stations:

1. Forward external port to Indigo server:
   ```
   External: <your-domain>:8088 → Internal: 192.168.100.160:8088
   ```

2. Configure remote gateway:
   ```
   Server IP: <your-domain> or <external-ip>
   Port: 8088
   ```

3. **Security Note:** Use HTTPS/VPN for remote access

### Integration with Other Systems

Device states can be accessed in:
- Indigo triggers (e.g., "if outdoor temperature < 0°C")
- Indigo action groups
- Indigo control pages
- External scripts via Indigo API

Example trigger:
```
If device "Rain Sensor" state "rainDaily" > 10:
    Send notification "Heavy rain today"
```

## Technical Details

### Architecture

```
Ecowitt Gateway → HTTP POST → Plugin HTTP Server → Parse Data → Update Indigo Devices
                  (30s interval)     (Port 8088)     (Python)      (Device States)
```

### HTTP Server

- Runs in separate thread
- Non-blocking socket operations
- Handles multiple concurrent requests
- Automatic error recovery

### Data Processing

1. HTTP POST received
2. URL-encoded data parsed
3. Fields mapped to device states
4. Units converted based on settings
5. Devices created/updated automatically

### Error Handling

- All operations wrapped in try/except
- Detailed error logging
- Graceful degradation
- Server continues on parse errors

## Known Limitations

1. **WH24 Support:** Limited testing, battery status may not be accurate
2. **WH45 CO2:** Only available with WH45 sensor (not WH41/WH43)
3. **WS90 Haptic Sensor:** Some advanced features not yet supported
4. **Historical Data:** Plugin only processes real-time data
5. **Custom Calibration:** Done at gateway level, not in plugin

## Comparison with Local API Method

| Feature                  | Custom Upload (This Plugin) | Local API (TCP)        |
|--------------------------|----------------------------|------------------------|
| Setup Complexity         | Easy                       | Complex                |
| Data Completeness        | Complete                   | Complete               |
| Update Frequency         | Configurable (16-60s)      | On-demand polling      |
| Gateway Configuration    | Yes (one-time)             | No                     |
| Network Traffic          | Push (gateway initiated)   | Pull (Indigo polls)    |
| Implementation           | HTTP Server                | Binary protocol parser |
| Reliability              | Very High                  | High                   |
| Battery Data             | Included                   | Included               |

## References

- [Ecowitt Official Website](https://www.ecowitt.com)
- [WS View App](https://www.ecowitt.com/shop/forum) (iOS/Android)
- [Ecowitt API Documentation](https://doc.ecowitt.net/web/#/apiv3en)
- [Weather Station Community](https://www.wxforum.net)

## Support

For issues or questions:

1. Check Indigo log with debug enabled
2. Verify gateway configuration in WS View app
3. Test with curl:
   ```bash
   curl -X POST http://192.168.100.160:8088/data/report/ \
        -d "tempf=72.5&humidity=65&baromrelin=29.92"
   ```
4. Review this README's troubleshooting section

## Version History

### Version 1.0 (2025-10-29)
- Initial release
- Support for all standard Ecowitt sensors
- Automatic device creation
- Metric/Imperial unit conversion
- HTTP server implementation
- Comprehensive error handling
- Battery status monitoring

## License

This plugin is provided as-is for use with Indigo Domotics home automation software.

## Credits

- Plugin developed by CliveS & Claude 4
- Based on Ecowitt protocol research from:
  - WeeWX GW1000 driver by Gary Roderick
  - ecowitt2mqtt by Aaron Bach
  - Various community contributions

---

**Enjoy your weather data in Indigo!** 🌤️
