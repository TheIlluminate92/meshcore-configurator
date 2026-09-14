"""Optional, explicitly advertised everyday-radio controls and local diagnostics."""
from datetime import datetime, timezone
from model import validate

EXTRA_KEYS = ('screen_timeout', 'screen_usb', 'usb_priority')
T1000_KEYS = ('buzzer_quiet', 'led_mode', 'usb_priority')

def discovered_settings(custom):
    if not isinstance(custom, dict):
        return {}
    if str(custom.get('t1000_ui')) == '1':
        keys = T1000_KEYS
    elif str(custom.get('ui_schema')) == '1' and str(custom.get('screen_min')) == '5' and str(custom.get('screen_max')) == '300':
        keys = EXTRA_KEYS
    else:
        return {}
    result = {}
    for key in keys:
        if key in custom:
            try: result.update(validate({key: custom[key]}))
            except (TypeError, ValueError): pass
    return result

async def read_diagnostics(port):
    from device import operate, event
    async def read(mc):
        result = {'port': port, 'captured_at': datetime.now(timezone.utc).isoformat(), 'errors': {}}
        for section, command, expected in (
            ('core', 'get_stats_core', 'STATS_CORE'),
            ('radio', 'get_stats_radio', 'STATS_RADIO'),
            ('packets', 'get_stats_packets', 'STATS_PACKETS')):
            try:
                result[section] = await event(getattr(mc.commands, command)(), expected)
            except Exception as exc:
                result['errors'][section] = str(exc)
        return result
    return await operate(port, read)

def format_diagnostics(result):
    lines = ['Radio diagnostics', str(result['port']), str(result['captured_at']),
             '', 'One-time local read. No radio test messages or background polling.', '']
    groups = (
        ('core', 'Device', {'battery_mv': 'Battery (mV)', 'uptime_secs': 'Uptime (seconds)', 'errors': 'Error flags', 'queue_len': 'Outgoing queue'}),
        ('radio', 'Radio', {'noise_floor': 'Noise floor (dBm)', 'last_rssi': 'Last received signal (dBm)', 'last_snr': 'Last signal/noise ratio (dB)', 'tx_air_secs': 'Transmit airtime (seconds)', 'rx_air_secs': 'Receive airtime (seconds)'}),
        ('packets', 'Packets', {'recv': 'Received', 'sent': 'Sent', 'flood_tx': 'Flood sent', 'direct_tx': 'Direct sent', 'flood_rx': 'Flood received', 'direct_rx': 'Direct received', 'recv_errors': 'Receive errors'}))
    for section, title, labels in groups:
        lines.append(title)
        for key, label in labels.items():
            value = result.get(section, {}).get(key)
            lines.append(f'  {label}: {value if value is not None else "Not reported"}')
        if section in result.get('errors', {}): lines.append('  Unavailable: ' + result['errors'][section])
        lines.append('')
    lines.append('Signal readings describe the last received packet, not a live link test.')
    return '\n'.join(lines)
