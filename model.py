"""Versioned profiles; browser exports use kHz/Hz, commands use MHz/kHz."""
import json
import math
import base64

FIELDS = {
    'name': ('Device name', str, None, None),
    'frequency': ('Frequency (MHz)', float, 150, 2500),
    'bandwidth': ('Bandwidth (kHz)', float, 7.8, 500),
    'spreading_factor': ('Spreading factor', int, 5, 12),
    'coding_rate': ('Coding rate', int, 5, 8),
    'tx_power': ('Transmit power (dBm)', int, -9, 22),
    'latitude': ('Latitude', float, -90, 90),
    'longitude': ('Longitude', float, -180, 180),
    'manual_add_contacts': ('Contact discovery mode', int, 0, 1),
    'advert_location_policy': ('Share location in adverts', int, 0, 1),
    'telemetry_mode_base': ('Device telemetry access', int, 0, 2),
    'telemetry_mode_loc': ('Location telemetry access', int, 0, 2),
    'telemetry_mode_env': ('Environment telemetry access', int, 0, 2),
    'multi_acks': ('Extra acknowledgement transmissions', int, 0, 3),
    'overwrite_oldest': ('Replace oldest non-favourite when full', int, 0, 1),
    'auto_add_chat': ('Auto-add companions', int, 0, 1),
    'auto_add_repeater': ('Auto-add repeaters', int, 0, 1),
    'auto_add_room_server': ('Auto-add room servers', int, 0, 1),
    'auto_add_sensor': ('Auto-add sensors', int, 0, 1),
    'auto_add_max_hops': ('Discovery reach', int, 0, 64),
    'gps': ('GPS receiver', int, 0, 1),
    'gps_interval': ('GPS update interval (seconds)', int, 1, 86400),
    'path_hash_mode': ('Path hash size', int, 0, 2),
    'buzzer_quiet': ('Buzzer', int, 0, 1),
    'motion_gps': ('Motion-aware GPS', int, 0, 3),
    'led_mode': ('Status LED on battery', int, 0, 2),
    'screen_timeout': ('Screen timeout (seconds)', int, 5, 300),
    'screen_usb': ('Keep screen awake on USB power', int, 0, 1),
    'usb_priority': ('USB configuration priority', int, 0, 1),
}
RADIO = ('frequency', 'bandwidth', 'spreading_factor', 'coding_rate')
COORDS = ('latitude', 'longitude')
OTHER = ('manual_add_contacts', 'advert_location_policy', 'telemetry_mode_base',
         'telemetry_mode_loc', 'telemetry_mode_env', 'multi_acks')
AUTO_BITS = {'overwrite_oldest': 1, 'auto_add_chat': 2, 'auto_add_repeater': 4,
             'auto_add_room_server': 8, 'auto_add_sensor': 16}
AUTO = tuple(AUTO_BITS) + ('auto_add_max_hops',)
CHOICES = {k: {0: 'Off', 1: 'On'} for k in (*AUTO_BITS, 'gps', 'advert_location_policy', 'screen_usb', 'usb_priority')}
# Editable suggestions preserve custom network values from existing profiles.
EDITABLE_CHOICES = {'frequency', 'bandwidth'}
CHOICES['buzzer_quiet'] = {0: 'Sounds enabled', 1: 'Muted'}
CHOICES['motion_gps'] = {0: 'Off — ordinary GPS', 1: 'Responsive', 2: 'Balanced', 3: 'Battery saver'}
CHOICES['led_mode'] = {0: 'Normal', 1: 'Unread messages only', 2: 'Quiet'}
CHOICES['frequency'] = {910.525: 'US / Canada — 910.525 MHz',
                        869.618: 'EU / UK narrow — 869.618 MHz',
                        869.525: 'EU / UK alternative — 869.525 MHz'}
CHOICES['bandwidth'] = {n: str(n) for n in (7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500)}
CHOICES['manual_add_contacts'] = {0: 'Automatically add all types', 1: 'Use selected types below / manual'}
for key in ('telemetry_mode_base', 'telemetry_mode_loc', 'telemetry_mode_env'):
    CHOICES[key] = {0: 'Deny', 1: 'Allowed contacts only', 2: 'Anyone'}
CHOICES['path_hash_mode'] = {0: '1 byte', 1: '2 bytes', 2: '3 bytes'}
CHOICES['auto_add_max_hops'] = {0: 'No limit', 1: 'Direct only', **{n: f'Up to {n-1} hops' for n in range(2, 65)}}
for key in ('spreading_factor', 'coding_rate', 'multi_acks'):
    CHOICES[key] = {n: str(n) for n in range(FIELDS[key][2], FIELDS[key][3]+1)}

def display(key, value):
    return CHOICES.get(key, {}).get(value, str(value))

def validate_naming(value=None):
    if value is None:return {'prefix':'Tracker','start':1}
    if not isinstance(value,dict) or set(value)!={'prefix','start'}:
        raise ValueError('Naming requires a prefix and starting number.')
    prefix=value['prefix']
    start=value['start']
    if not isinstance(prefix,str) or not prefix.strip() or '\x00' in prefix or len(prefix.strip().encode('utf-8'))>24:
        raise ValueError('Naming prefix must contain 1–24 UTF-8 bytes, without null characters.')
    if type(start) is not int or not 1<=start<=999999:
        raise ValueError('Starting number must be a whole number from 1 to 999999.')
    return {'prefix':prefix.strip(),'start':start}

def parse_input(key, text):
    if not isinstance(text, str) or key not in CHOICES:
        return text
    text = text.strip()
    for value, label in CHOICES.get(key, {}).items():
        if text.casefold() == label.casefold():
            return value
    try:
        number = float(text)
        for value in CHOICES.get(key, {}):
            if number == value:
                return value
    except ValueError:
        pass
    return text

def validate(settings, maximum_power=22):
    if not isinstance(settings, dict):
        raise ValueError('Settings must be a JSON object.')
    result = {}
    for key, value in settings.items():
        if key not in FIELDS:
            raise ValueError(f'Unsupported editable option: {key}')
        label, kind, low, high = FIELDS[key]
        if kind is str:
            if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value.encode('utf-8')) > 31:
                raise ValueError('Name must contain 1–31 UTF-8 bytes and no null characters.')
            result[key] = value
            continue
        if isinstance(value, bool) and key in CHOICES and FIELDS[key][3] == 1:
            value = int(value)
        if isinstance(value, bool):
            raise ValueError(f'{label} must be a number.')
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f'{label} must be a number.') from None
        if key == 'tx_power':
            high = min(high, maximum_power)
        if not math.isfinite(number) or not low <= number <= high or (kind is int and not number.is_integer()):
            raise ValueError(f'{label} must be {low} to {high}' + (' (whole number).' if kind is int else '.'))
        result[key] = kind(number)
    return result

def load_profile(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Profile must be a JSON object.')
    from compatibility import check_role
    check_role(data)
    if 'schema_version' in data:
        if type(data['schema_version']) is not int or data['schema_version'] not in (1, 2) or data.get('format') != 'meshcore-usb-profile':
            raise ValueError('Unrecognized profile format or version.')
        units = data.get('units', {})
        expected = {'frequency': 'MHz', 'bandwidth': 'kHz', 'tx_power': 'dBm'}
        if not isinstance(units, dict) or any(k in units and units[k] != v for k, v in expected.items()):
            raise ValueError('Profile units must be MHz, kHz and dBm.')
        return validate(data.get('settings'))
    if not {'name', 'radio_settings', 'position_settings'} <= data.keys():
        raise ValueError('Expected a MeshCore browser export or configurator profile.')
    radio = data['radio_settings']
    values = {'name': data['name']}
    for key in RADIO + ('tx_power',):
        if key in radio:
            values[key] = radio[key] / (1000 if key in ('frequency', 'bandwidth') else 1)
    values.update({k: v for k, v in data['position_settings'].items() if k in COORDS})
    for section in ('other_settings', 'auto_add_settings'):
        values.update({k: v for k, v in data.get(section, {}).items() if k in FIELDS})
    return validate(values)

def profile(settings, channels=None):
    result = {'format': 'meshcore-usb-profile', 'schema_version': 2,
            'units': {'frequency': 'MHz', 'bandwidth': 'kHz', 'tx_power': 'dBm'},
            'settings': validate(settings)}
    if channels is not None:
        result['channels'] = validate_channels(channels)
    return result

def validate_channels(channels):
    if not isinstance(channels, list):
        raise ValueError('Channels must be a list.')
    result, seen = [], set()
    for channel in channels:
        if not isinstance(channel, dict) or set(channel) != {'index', 'name', 'secret'}:
            raise ValueError('Each channel requires index, name and secret.')
        index, name, secret = channel['index'], channel['name'], channel['secret']
        if type(index) is not int or not 0 <= index <= 63 or index in seen:
            raise ValueError('Channel indexes must be unique numbers from 0 to 63.')
        if not isinstance(name, str) or '\x00' in name or len(name.encode('utf-8')) > 31:
            raise ValueError('Channel names must be at most 31 UTF-8 bytes.')
        try:
            if not isinstance(secret, str) or len(secret) != 32:
                raise ValueError()
            raw = bytes.fromhex(secret)
            if len(raw) != 16:
                raise ValueError()
        except ValueError:
            raise ValueError('Channel keys must contain exactly 32 hexadecimal characters.') from None
        seen.add(index)
        result.append({'index': index, 'name': name, 'secret': raw.hex()})
    return result

def load_document(path):
    settings = load_profile(path)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    channels = data.get('channels', [])
    warnings = []
    if data.get('format') != 'meshcore-usb-profile':
        converted = []
        for index, channel in enumerate(channels):
            secret = channel.get('secret', '')
            try:
                raw = bytes.fromhex(secret) if len(secret) == 32 else base64.b64decode(secret, validate=True)
            except (ValueError, TypeError):
                raise ValueError(f'Invalid key in channel slot {index}.') from None
            converted.append({'index': index, 'name': channel['name'], 'secret': raw.hex()})
        channels = converted
        warnings.append('Browser channel order maps to numbered device slots. Review each slot before applying. Contacts, identity, region metadata and message retention are not imported.')
    return settings, validate_channels(channels), warnings

def equal(key, a, b):
    if key in ('frequency', 'bandwidth'):
        return round(float(a) * 1000) == round(float(b) * 1000)
    if key in COORDS:
        return round(float(a) * 1e6) == round(float(b) * 1e6)
    return a == b

def changes(current, desired):
    return {k: v for k, v in desired.items() if k not in current or not equal(k, current[k], v)}
