"""Portable fleet contact-card library and contact-list exports."""
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from storage import atomic_text

SCHEMA = 1
HEX_KEY = re.compile(r'^[0-9a-f]{64}$')


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(value):
    if isinstance(value, bytes):
        value = value.hex()
    value = str(value).strip().lower()
    if not HEX_KEY.fullmatch(value):
        raise ValueError('Contact identity is not a 32-byte public key.')
    return value


def card_bytes(uri):
    if not isinstance(uri, str) or not uri.lower().startswith('meshcore://'):
        raise ValueError('Contact card is not a MeshCore URI.')
    encoded = uri.split('://', 1)[1].strip()
    if not encoded or len(encoded) % 2 or len(encoded) > 8192:
        raise ValueError('Contact card has an invalid length.')
    try:
        raw = bytes.fromhex(encoded)
    except ValueError as exc:
        raise ValueError('Contact card contains invalid data.') from exc
    # MeshCore card = encoded advert packet. Bind the saved URI to the public
    # identity learned from SELF_INFO so a damaged library cannot add a
    # different, valid card and leave it behind before read-back catches it.
    if len(raw) < 102 or ((raw[0] >> 2) & 0x0f) != 4:
        raise ValueError('Contact card is not a complete MeshCore advertisement.')
    route = raw[0] & 0x03
    offset = 5 if route in (0, 3) else 1
    if offset >= len(raw): raise ValueError('Contact card is truncated.')
    path = raw[offset]; offset += 1
    hash_size, hash_count = (path >> 6) + 1, path & 63
    if hash_size == 4: raise ValueError('Contact card has an unsupported path encoding.')
    offset += hash_size * hash_count
    if offset + 100 > len(raw): raise ValueError('Contact card is truncated.')
    return raw


def card_identity(uri):
    raw = card_bytes(uri)
    route = raw[0] & 0x03
    offset = 5 if route in (0, 3) else 1
    path = raw[offset]; offset += 1 + ((path >> 6) + 1) * (path & 63)
    return raw[offset:offset+32].hex()


class FleetContactStore:
    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        if not self.path.exists():
            return {'schema': SCHEMA, 'contacts': {}}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('The fleet contact library could not be read. Restore it from a portable backup or rename the damaged file.') from exc
        if data.get('schema') != SCHEMA or not isinstance(data.get('contacts'), dict):
            raise ValueError('The fleet contact library was created by an incompatible app version.')
        return data

    def entries(self):
        values = []
        for key, item in self._load()['contacts'].items():
            try:
                clean = dict(item)
                clean['public_key'] = identity(key)
                card_bytes(clean['contact_uri'])
                values.append(clean)
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(values, key=lambda item: (item.get('name', '').casefold(), item['public_key']))

    def remember(self, snapshot):
        uri = snapshot.get('self_contact_uri')
        if not uri:
            return False
        key = identity(snapshot['self_info']['public_key'])
        if card_identity(uri) != key:
            raise ValueError('The exported contact card does not match this radio identity.')
        data = self._load()
        old = data['contacts'].get(key, {})
        stamp = now()
        data['contacts'][key] = {
            'public_key': key,
            'name': str(snapshot.get('settings', {}).get('name', '?')),
            'model': str(snapshot.get('device', {}).get('model', 'Unknown radio')),
            'firmware': str(snapshot.get('device', {}).get('ver', '?')),
            'contact_uri': uri,
            'first_seen': old.get('first_seen', stamp),
            'last_seen': stamp,
        }
        atomic_text(self.path, json.dumps(data, indent=2, sort_keys=True))
        return True


def contact_rows(snapshot):
    contacts = snapshot.get('contacts', {})
    if not isinstance(contacts, dict):
        return []
    rows = []
    for key, value in contacts.items():
        if not isinstance(value, dict):
            continue
        row = dict(value)
        row['public_key'] = str(row.get('public_key', key))
        rows.append(row)
    return sorted(rows, key=lambda item: (str(item.get('adv_name', '')).casefold(), item['public_key']))


def export_contact_list(path, snapshot):
    path = Path(path)
    rows = contact_rows(snapshot)
    if path.suffix.lower() == '.csv':
        columns = ('adv_name', 'type', 'public_key', 'flags', 'out_path_hash_mode',
                   'out_path_len', 'out_path', 'last_advert', 'adv_lat', 'adv_lon', 'lastmod')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                # Prevent a radio name beginning with a spreadsheet formula
                # marker from becoming executable content when opened in Excel.
                writer.writerow({key: ("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value)
                                 for key,value in row.items()})
    else:
        atomic_text(path, json.dumps({
            'format': 'meshcore-contact-list',
            'exported_at': now(),
            'source': {
                'name': snapshot.get('settings', {}).get('name', '?'),
                'public_key': snapshot.get('self_info', {}).get('public_key', ''),
                'model': snapshot.get('device', {}).get('model', '?'),
            },
            'contacts': rows,
        }, indent=2, default=str))
    return len(rows)
