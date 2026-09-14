# Motion-aware GPS — experimental implementation

T1000-E only, v1.17.1-t1000-dual.4. Off by default. This is a GPS power policy, not a location broadcasting scheduler. Ordinary GPS remains available at any time.

| Preset | Still before sleeping | Refresh after sleeping |
|---|---:|---:|
| Off | Ordinary GPS | Ordinary GPS |
| Responsive | 10 minutes | 5 minutes |
| Balanced | 3 minutes | 15 minutes |
| Battery saver | 1 minute | 30 minutes |

Two acceleration changes above 40 mg within one second confirm motion. Polling is every 250 ms with the accelerometer configured at 100 Hz, ±8g. Movement wakes sleeping GPS; GPS still needs time and sky visibility for a fix. A stationary refresh sleeps again after obtaining a fresh fix. No fix for two minutes causes a five-minute backoff even while moving, to bound poor-sky power use. Last known coordinates remain available and must not be interpreted as a fresh fix. Manual GPS Off overrides every preset.

The driver checks QMA6100P identity 0x90 at address 0x12 before register writes. Missing, unknown, invalid-data or failed sensors fall back to ordinary GPS. Disable/re-enable the mode to retry. Software I2C uses bounded waits; motion initialization is staged. Off does not initialize the accelerometer. The GPS's existing wake sequence retains its short delays. No added flash writes occur on motion events.

## Protocol and configurator

GET_CUSTOM_VARS advertises motion_schema:1 and motion_gps:0..3. SET_CUSTOM_VAR persists motion_gps. The PC exposes the field only with t1000_ui:1 AND motion_schema:1; supported settings are reread after writes, including batch writes. Location & GPS contains the preset selector.

Read-only snapshot values: motion_state 0 manual-off, 1 normal, 2 acquiring, 3 tracking, 4 sleeping, 5 backoff, 6 sensor-fault. motion_sensor 0 pending/off, 1 ready, 2 fault. The gps setting is the requested switch, not temporary physical sleep state.

## Hardware evidence and limits

Register initialization is based on [Seeed's QMA6100P example](https://github.com/Seeed-Studio/Adafruit_nRF52_Arduino/tree/master/libraries/Tracker_T1000_E_LoRaWAN_Examples/src/accelerometer). Pins follow the [T1000-E documentation](https://wiki.seeedstudio.com/t1000_e_intro/): SDA 26, SCL 27, sensor power 39. The example targets a LoRaWAN variant; runtime identity checking guards differences. No manufacturer example firmware is installed. Interrupt wiring is not assumed.

This build has not been tested on physical hardware. Emulation does not validate I2C waveforms, motion sensitivity, real GNSS acquisition, BLE timing or power consumption. Smooth constant-speed travel can look stationary; this is intended for a carried radio, not guaranteed vehicle tracking. Test one unit outside, then stationary, then walking; compare against Off and measure a full battery run before updating the other five. Keep the tested dual.2 recovery package.
