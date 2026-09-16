# V4 candidate support — 0.7.5

- USB, Bluetooth and Wi-Fi (TCP) connections use the same Companion read/apply/verify adapter.
- Read the radio over USB/BLE, then select **Wi-Fi setup**. Only firmware advertising
  `wifi_schema:1` is accepted. SSID/password/port/enabled state are submitted as one
  bounded record. Identity is checked before sending and after saving; enabled/SSID/port are reread.
- Password is write-only and is not included in profiles, snapshots or support
  reports. Enter it again when saving. Blank means an open network, not "keep old".
- Reread the radio after network association for `wifi_ip` in Device data. Select
  Wi-Fi and enter that address (default port 5000). No network-wide scan is performed.
- Use a trusted LAN. Companion TCP has no application authentication or encryption.
- Keep one active configuration writer at a time; USB/BLE/Wi-Fi share Companion state.
- Advanced tab adds receive delay (0–20) and airtime budget (0–9), matching the
  firmware's startup clamps. Values are written together with 0.001 resolution
  and both reread. Unsupported values remain read-only.
- Existing JSON profiles, channel editing, batch verification and device identity
  protection remain in use. Network credentials are intentionally separate from
  shared mesh profiles.

Firmware build options and unsupported controls are mapped in the private firmware
repository's `docs/HELTEC_V4.md`. No new RX gain, FEM gain, repeat-mode, identity-key
or display controls are claimed by this candidate.

V4/V4 R8 firmware **triple.3** adds a Wi-Fi page immediately after Bluetooth on
the OLED. Short-press USR to navigate, then hold about 1.2 seconds to toggle.
On the Wi-Fi page this acts as the toggle, including during startup. A long press
with the screen asleep only wakes it. Configure the network once on the PC;
the radio retains the network and enabled state across restarts. Reread in the
configurator after a toggle. Turning Wi-Fi off disconnects TCP; finish any write
first. USB/BLE settings remain unchanged. No automatic idle shutdown is added.
No configurator code update beyond 0.7.5 is required for this firmware change.

Firmware hardware validation is pending. The configurator does not flash the
radio automatically.
