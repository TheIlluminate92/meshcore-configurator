# V4 candidate support — 0.7.5-dev

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

Planned V4 firmware control: manual Wi-Fi on/off on the radio itself, with
remembered state/network and visible connection status. USB/BLE should remain
available when Wi-Fi is off. Automatic Wi-Fi idle shutdown is outside the
requested scope. The on-device toggle is not implemented in this candidate;
current Wi-Fi enable/disable is through the PC setup dialog.

Hardware validation is pending. This development app does not replace the public
stable release or flash the radio automatically.
