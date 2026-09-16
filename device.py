"""Read/write adapter for supported MeshCore Companion commands over USB."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import json
import struct
import re
from model import RADIO, COORDS, OTHER, AUTO, AUTO_BITS, FIELDS, validate, validate_channels, changes

MAP = {'name': 'name', 'frequency': 'radio_freq', 'bandwidth': 'radio_bw',
       'spreading_factor': 'radio_sf', 'coding_rate': 'radio_cr',
       'tx_power': 'tx_power', 'latitude': 'adv_lat', 'longitude': 'adv_lon'}
MAP.update({k: ('adv_loc_policy' if k == 'advert_location_policy' else k) for k in OTHER})

def radio_packet(values, repeat=None):
    packet = struct.pack('<BIIBB', 11, round(values['frequency'] * 1000),
                         round(values['bandwidth'] * 1000), values['spreading_factor'], values['coding_rate'])
    return packet if repeat is None else packet + bytes([int(repeat)])

def coordinates_packet(values):
    return struct.pack('<Biii', 14, round(values['latitude'] * 1e6), round(values['longitude'] * 1e6), 0)

async def send_config(mc, packet):
    from meshcore import EventType
    return await mc.commands.send(packet, [EventType.OK, EventType.ERROR])

def supported_value(key, value):
    try:
        return validate({key: value})[key]
    except ValueError:
        return None

def serial_ports():
    from serial.tools import list_ports
    return [(p.device, p.description) for p in list_ports.comports()]

async def bluetooth_devices():
    from bleak import BleakScanner
    from meshcore.ble_cx import UART_SERVICE_UUID
    try:
        found = await BleakScanner.discover(timeout=8, return_adv=True)
    except Exception as exc:
        raise RuntimeError('Bluetooth scan failed. Check that Windows Bluetooth is turned on and a Bluetooth adapter is available. Then try Find devices again. Details: ' + str(exc)) from exc
    return sorted([(f'ble:{dev.address}', adv.local_name or dev.name or 'BLE Companion')
                   for dev, adv in found.values()
                   if UART_SERVICE_UUID.lower() in [u.lower() for u in adv.service_uuids]
                   or (adv.local_name or dev.name or '').lower().startswith('meshcore')])

def make_connection(port):
    if port.startswith('tcp://'):
        from wifi_setup import endpoint
        from tcp_connection import ClosingTCPConnection
        host, number = endpoint(port)
        return ClosingTCPConnection(host, number)
    if port.startswith('ble:'):
        from meshcore import BLEConnection
        # This library uses a non-None pin flag to request OS pairing.
        # Windows handles PIN entry; no PIN is stored by this app.
        return BLEConnection(address=port[4:], pin=True)
    from serial_connection import ClosingSerialConnection
    return ClosingSerialConnection(port, 115200)

def save_json(path, data):
    from storage import atomic_text
    atomic_text(path,json.dumps(data, indent=2, default=lambda x: x.hex() if isinstance(x, bytes) else str(x)))

async def event(call, expected):
    reply = await asyncio.wait_for(call, 15)
    if reply is None or reply.type.name != expected:
        raise RuntimeError(f'Expected {expected}: {getattr(reply, "payload", "no reply")}')
    return reply.payload

async def basic(mc, port):
    info = await event(mc.commands.send_device_query(), 'DEVICE_INFO')
    own = await event(mc.commands.send_appstart(), 'SELF_INFO')
    # The library exposes the signed firmware byte as unsigned.
    if 128 <= own.get('tx_power', 0) <= 255:
        own['tx_power'] -= 256
    snapshot = {'firmware_role':'companion', 'captured_at': datetime.now(timezone.utc).isoformat(), 'port': port,
            'device': info, 'self_info': own,
            'settings': {k: own[v] for k, v in MAP.items() if v in own}}
    # Normalize booleans and keep out-of-range/new enum values read-only.
    snapshot['settings'] = {k: supported_value(k, v) for k, v in snapshot['settings'].items()}
    snapshot['settings'] = {k: v for k, v in snapshot['settings'].items() if v is not None}
    snapshot['read_errors'] = {}
    for section, method, expected in [('custom_vars', mc.commands.get_custom_vars, 'CUSTOM_VARS'),
                                     ('auto_add', mc.commands.get_autoadd_config, 'AUTOADD_CONFIG')]:
        try:
            snapshot[section] = await event(method(), expected)
        except Exception as exc:
            snapshot['read_errors'][section] = str(exc)
    custom = snapshot.get('custom_vars', {})
    for k in ('gps', 'gps_interval'):
        if k in custom and supported_value(k, custom[k]) is not None:
            snapshot['settings'][k] = supported_value(k, custom[k])
    # Opt in only on the exact extension schema and bounds we understand.
    from radio_extras import discovered_settings
    snapshot['settings'].update(discovered_settings(custom))
    if hasattr(mc.commands, 'get_tuning'):
        try:
            tuning = await event(mc.commands.get_tuning(), 'TUNING_PARAMS')
            snapshot['tuning'] = tuning
            for key in ('rx_delay', 'airtime_factor'):
                if key in tuning:
                    value = supported_value(key, tuning[key] / 1000)
                    if value is not None: snapshot['settings'][key] = value
        except Exception as exc:
            snapshot['read_errors']['tuning'] = str(exc)
    auto = snapshot.get('auto_add', {})
    if 'config' in auto:
        snapshot['settings'].update({k: int(bool(auto['config'] & bit)) for k, bit in AUTO_BITS.items()})
    if 'max_hops' in auto and supported_value('auto_add_max_hops', auto['max_hops']) is not None:
        snapshot['settings']['auto_add_max_hops'] = auto['max_hops']
    if 'path_hash_mode' in info and supported_value('path_hash_mode', info['path_hash_mode']) is not None:
        snapshot['settings']['path_hash_mode'] = info['path_hash_mode']
    return snapshot

async def read_channel(mc, index):
    payload = await event(mc.commands.get_channel(index), 'CHANNEL_INFO')
    if payload.get('channel_idx') != index:
        raise RuntimeError('Channel reply has an unexpected slot number.')
    secret = payload['channel_secret']
    return {'index': index, 'name': payload['channel_name'],
            'secret': secret.hex() if isinstance(secret, bytes) else secret}

async def operate(port, action):
    from meshcore import MeshCore
    connection = make_connection(port)
    mc = MeshCore(connection, only_error=True, default_timeout=5, auto_reconnect=False)
    try:
        try:
            response = await asyncio.wait_for(mc.connect(), 90 if port.startswith('ble:') else 15)
        except Exception as exc:
            if port.startswith('ble:'):
                raise RuntimeError('Bluetooth connection failed. Enable BLE Companion firmware, close other connections, and complete Windows pairing if prompted. No configuration commands were sent by this operation.') from exc
            if isinstance(exc, PermissionError) or 'Access is denied' in str(exc):
                raise RuntimeError(f'{port} is busy or Windows denied access. Close other browser/app connections to this port. If an older configurator is open, close it and reopen the updated version. No configuration commands were sent by this operation.') from exc
            raise
        if response is None:
            raise RuntimeError('No Companion response. Check the selected device, firmware connection mode, and other app connections.')
        return await action(mc)
    finally:
        import sys
        primary=sys.exception();cleanup_errors=[]
        if primary:
            from diagnostics import record_error
            record_error('device',primary)
        # Bound cleanup and always try both layers, including partial connects.
        for disconnect in (mc.disconnect,connection.disconnect):
            try:await asyncio.wait_for(disconnect(),10)
            except Exception as exc:cleanup_errors.append(str(exc) or type(exc).__name__)
        if cleanup_errors:
            detail='Connection cleanup failed: '+'; '.join(cleanup_errors)
            if primary is not None:primary.add_note(detail)
            else:raise RuntimeError(detail+'. Reconnect and reread before another operation.')

async def read_device(port):
    async def read(mc):
        snapshot = await basic(mc, port)
        for name, method, expected in [('contacts', mc.commands.get_contacts, 'CONTACTS')]:
            try:
                snapshot[name] = await event(method(), expected)
            except Exception as exc:
                snapshot['read_errors'][name] = str(exc)
        snapshot['channels'] = []
        count = snapshot['device'].get('max_channels', 0)
        for index in range(min(count, 64)):
            try:
                snapshot['channels'].append(await read_channel(mc, index))
            except Exception as exc:
                snapshot['read_errors'][f'channel_{index}'] = str(exc)
                break
        return snapshot
    return await operate(port, read)

async def apply_device(port, baseline, desired, report_dir, channels=None):
    """One device per transaction; no retries or rollback after uncertain writes."""
    async def apply(mc):
        current = await basic(mc, port)
        if current['self_info']['public_key'] != baseline['self_info']['public_key']:
            raise ValueError('A different device is connected. Read it before applying.')
        stale_fields = dict(baseline['settings'])
        if current['settings'].get('gps') == 1:
            for k in COORDS:
                stale_fields.pop(k, None)
        if changes(current['settings'], stale_fields):
            raise ValueError('Device settings changed since the last read. Read and review again.')
        values = validate(desired, current['self_info'].get('max_tx_power', 0))
        if set(values) - set(current['settings']):
            raise ValueError('Profile contains settings this device did not report.')
        delta = changes(current['settings'], values)
        radio_changed = bool(set(RADIO) & delta.keys())
        if radio_changed and current['device'].get('fw ver', 0) >= 9:
            if type(current['device'].get('repeat')) is not bool:
                raise ValueError('Device did not report repeat mode. Radio editing is blocked to avoid changing it inadvertently.')
            if current['device']['repeat'] != baseline['device'].get('repeat'):
                raise ValueError('Repeat mode changed since the last read. Read and review again.')
        merged = current['settings'] | values
        if set(COORDS) & delta.keys() and merged.get('gps') == 1:
            raise ValueError('Turn GPS off before setting a fixed location, or leave coordinates unchanged.')
        for group in (RADIO, COORDS):
            if set(group) & delta.keys() and not set(group) <= merged.keys():
                raise ValueError('Device did not report all fields needed by this command.')
        if set(OTHER) & delta.keys() and not all(MAP[k] in current['self_info'] for k in OTHER):
            raise ValueError('Device did not return the complete shared contact/telemetry settings group.')
        channel_delta = []
        known_channels = {c['index']: c for c in baseline.get('channels', [])}
        for requested in validate_channels(channels or []):
            index = requested['index']
            if index not in known_channels:
                raise ValueError(f'Channel slot {index} was not read successfully.')
            actual = await read_channel(mc, index)
            if actual != known_channels[index]:
                raise ValueError(f'Channel slot {index} changed since the last read.')
            if actual != requested:
                channel_delta.append(requested)
        report = {'before': current, 'requested': delta, 'acknowledged': [], 'verified': False}
        report['channels_before'] = list(known_channels.values())
        report['channels_requested'] = channel_delta
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        report_path = Path(report_dir) / f'apply-{re.sub(r"[^A-Za-z0-9_-]", "_", port)}-{stamp}.json'
        save_json(report_path, report)
        try:
            jobs = []
            if {'rx_delay', 'airtime_factor'} & delta.keys():
                if not {'rx_delay', 'airtime_factor'} <= current['settings'].keys():
                    raise ValueError('Both tuning settings must be read before either can be changed.')
                jobs.append(('tuning', lambda: mc.commands.set_tuning(
                    round(merged['rx_delay'] * 1000), round(merged['airtime_factor'] * 1000))))
            for key in ('gps', 'gps_interval', 'screen_timeout', 'screen_usb', 'usb_priority', 'buzzer_quiet', 'led_mode', 'motion_gps'):
                if key in delta:
                    jobs.append((key, lambda k=key: mc.commands.set_custom_var(k, str(merged[k]))))
            if 'name' in delta:
                jobs.append(('name', lambda: mc.commands.set_name(merged['name'])))
            if set(RADIO) & delta.keys():
                jobs.append(('radio', lambda: send_config(mc, radio_packet(merged,
                            repeat=current['device']['repeat'] if current['device'].get('fw ver', 0) >= 9 else None))))
            if 'tx_power' in delta:
                jobs.append(('tx_power', lambda: send_config(mc, struct.pack('<Bb', 12, merged['tx_power']))))
            if set(COORDS) & delta.keys():
                jobs.append(('coordinates', lambda: send_config(mc, coordinates_packet(merged))))
            if set(OTHER) & delta.keys():
                shared = dict(current['self_info'])
                shared.update({MAP[k]: merged[k] for k in OTHER if k in merged})
                jobs.append(('contact/telemetry settings', lambda: mc.commands.set_other_params_from_infos(shared)))
            if set(AUTO) & delta.keys():
                # Retain unrecognized flag bits, and send max_hops only if read.
                from meshcore import EventType
                flags = current['auto_add']['config']
                for key, bit in AUTO_BITS.items():
                    flags = (flags | bit) if merged[key] else (flags & ~bit)
                packet = bytes([58, flags])
                if 'auto_add_max_hops' in merged:
                    packet += bytes([merged['auto_add_max_hops']])
                jobs.append(('contact discovery filters', lambda: mc.commands.send(packet, [EventType.OK, EventType.ERROR])))
            if 'path_hash_mode' in delta:
                jobs.append(('path hash mode', lambda: mc.commands.set_path_hash_mode(merged['path_hash_mode'])))
            for channel in channel_delta:
                from meshcore import EventType
                # Send the explicit secret, including for # channels; the library
                # convenience setter otherwise silently derives a different key.
                wire = bytes([32, channel['index']]) + channel['name'].encode('utf-8').ljust(32, b'\0') + bytes.fromhex(channel['secret'])
                jobs.append((f"channel {channel['index']}", lambda p=wire: mc.commands.send(p, [EventType.OK, EventType.ERROR])))
            for label, command in jobs:
                await event(command(), 'OK')
                report['acknowledged'].append(label)
                save_json(report_path, report)
            after = await basic(mc, port)
            report['after'] = after
            if after['self_info'].get('public_key') != current['self_info'].get('public_key'):
                raise RuntimeError('Read-back identity mismatch. The radio could not be verified.')
            if set(OTHER) & delta.keys():
                if any(after['self_info'].get(MAP[k]) != shared[MAP[k]] for k in OTHER):
                    raise RuntimeError('Read-back mismatch in shared contact/telemetry settings.')
            if set(AUTO) & delta.keys():
                if after.get('auto_add', {}).get('config') != flags:
                    raise RuntimeError('Read-back mismatch in contact discovery flags.')
                if 'auto_add_max_hops' in merged and after.get('auto_add', {}).get('max_hops') != merged['auto_add_max_hops']:
                    raise RuntimeError('Read-back mismatch in contact discovery reach.')
            if radio_changed and current['device'].get('fw ver', 0) >= 9:
                if after['device'].get('repeat') != current['device']['repeat']:
                    raise RuntimeError('Read-back mismatch: repeat mode was not preserved.')
            expected = dict(values)
            if {'rx_delay', 'airtime_factor'} & delta.keys():
                expected.update({key: round(merged[key]*1000)/1000 for key in ('rx_delay','airtime_factor')})
            for group in (RADIO, COORDS):
                if set(group) & delta.keys():
                    expected.update({k: merged[k] for k in group})
            mismatch = changes(after['settings'], expected)
            if after['settings'].get('gps') == 1:
                for key in COORDS:
                    if key not in delta:
                        mismatch.pop(key, None)
            if mismatch:
                raise RuntimeError(f'Read-back mismatch in: {", ".join(mismatch)}')
            after_channels = dict(known_channels)
            for channel in validate_channels(channels or []):
                actual = await read_channel(mc, channel['index'])
                if actual != channel:
                    raise RuntimeError(f"Read-back mismatch in channel slot {channel['index']}")
                after_channels[channel['index']] = actual
            after['channels'] = list(after_channels.values())
            after['snapshot_scope'] = {
                'kind': 'apply_verification',
                'settings': 'Reread after applying',
                'channels_reread': [c['index'] for c in validate_channels(channels or [])],
                'other_channels': 'Retained from the previous read; not refreshed',
                'contacts': 'Not included; use Read device for a fresh full snapshot',
            }
            report['verified'] = True
            return after
        except Exception as exc:
            report['error'] = str(exc)
            raise RuntimeError(f'{exc}\nSome settings may have changed. Read the device again.\nReport: {report_path}') from exc
        finally:
            save_json(report_path, report)
    return await operate(port, apply)
