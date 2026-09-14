# Everyday radio controls — development build

Version 0.7.1-dev. This is a candidate for local testing, not a published update.

Compatible custom firmware can advertise three optional controls on Screen &
USB: screen timeout (5–300 seconds), keep an awake screen on USB power, and
USB configuration priority. Defaults remain unchanged. Unreported/unknown
capabilities stay disabled; profile and batch writes require reread verification.
USB priority pauses BLE commands while a USB app has the serial port open.
Close the port or unplug to restore BLE command access. It does not provide
independent simultaneous client sessions.

Help > Radio diagnostics reads local battery voltage, uptime, radio and packet
counters on demand. Unsupported replies show Not reported. No background
polling or mesh test traffic. Last RSSI/SNR describe the last received packet.

Capability schema 1 is an allow-listed extension using custom variables with
explicit version and timeout bounds. Future unknown schemas remain read-only.
This does not permit arbitrary firmware-provided commands or UI code.

Local validation: 122 tests passed; packaged EXE starts with 26 settings and
history available. Physical radio behavior and battery life require bench tests.
The portable EXE keeps user information in User Data beside it as before.
