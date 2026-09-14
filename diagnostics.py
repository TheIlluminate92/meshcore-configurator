"""Bounded, privacy-preserving diagnostics: never log exception messages or locals."""
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
import platform
import traceback
import threading
import zipfile
from app_version import VERSION
from app_paths import DATA_ROOT
from model import FIELDS

_LOCK = threading.RLock()
REASONS = {'port_access','timeout','readback_mismatch','identity_changed','stale_read','checksum_mismatch','no_companion_response','unclassified'}

def reason(exc):
    message=str(exc).lower()
    for token, code in [('access is denied','port_access'),('busy or windows','port_access'),('timeout','timeout'),('timed out','timeout'),('read-back mismatch','readback_mismatch'),('different device','identity_changed'),('changed since','stale_read'),('checksum','checksum_mismatch'),('no companion response','no_companion_response')]:
        if token in message:return code
    return 'unclassified'

CONTEXTS = {'device', 'batch', 'interface', 'update', 'profiles', 'history', 'startup', 'support'}


def record_error(context, exc, folder=None):
    try:
        folder = Path(folder or DATA_ROOT) / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        frames = traceback.extract_tb(exc.__traceback__)
        data = {'time': datetime.now(timezone.utc).isoformat(), 'version': VERSION,
                'context': context if context in CONTEXTS else 'interface', 'reason':reason(exc),
                'kind': type(exc).__name__ if type(exc).__name__ in {'ValueError','RuntimeError','OSError','PermissionError','TimeoutError','SerialException','SerialTimeoutException','BleakError','TclError','KeyError','TypeError','AttributeError','FileNotFoundError'} else 'Exception',
                'errno': getattr(exc, 'errno', None) if type(getattr(exc, 'errno', None)) is int else None,
                'frames': [{'module': Path(f.filename).stem, 'line': f.lineno} for f in frames if Path(f.filename).parent == Path(__file__).parent]}
        with _LOCK:
            handler = RotatingFileHandler(folder / 'errors.jsonl', maxBytes=128*1024, backupCount=2, encoding='utf-8')
            try:
                handler.emit(logging.LogRecord('meshcore', logging.ERROR, '', 0, json.dumps(data), (), None))
            finally:
                handler.close()
    except Exception:
        pass  # A logging failure must not prevent device cleanup or shutdown.


def support_report(path, snapshot=None, folder=None):
    folder = Path(folder or DATA_ROOT)
    events = []
    for name in ('errors.jsonl.2','errors.jsonl.1','errors.jsonl'):
        log=folder/'logs'/name
        if not log.exists() or log.stat().st_size > 256*1024:continue
        for line in log.read_text(encoding='utf-8', errors='replace').splitlines()[-300:]:
            try:
                e = json.loads(line)
                # Only generated categories and numeric metadata cross the export boundary.
                events.append({'reason':e.get('reason') if e.get('reason') in REASONS else 'unclassified','context': e['context'] if e.get('context') in CONTEXTS else 'interface',
                               'kind': e.get('kind') if e.get('kind') in {'ValueError','RuntimeError','OSError','PermissionError','TimeoutError','SerialException','SerialTimeoutException','BleakError','TclError','KeyError','TypeError','AttributeError','FileNotFoundError'} else 'Exception',
                               'errno': e.get('errno') if type(e.get('errno')) is int else None,
                               'time': e.get('time') if isinstance(e.get('time'),str) and __import__('re').fullmatch(r'[0-9T:.+Z-]{10,40}', e['time']) else None,
                               'frames': [{'module': f['module'], 'line': f['line']} for f in e.get('frames', []) if f.get('module') in {'app','device','serial_connection','batch','batch_ui','batch_editor','model','updater','update_ui','profile_library','library_ui','history_store','history_ui','restore','restore_ui','diagnostics','desktop_entry'} and type(f.get('line')) is int]})
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
    snapshot = snapshot or {}
    device = snapshot.get('device', {})
    summary = {'format': 'meshcore-support-report', 'version': VERSION,
               'created': datetime.now(timezone.utc).isoformat(), 'system': platform.system(),
               'os_release': platform.release(), 'python': platform.python_version(),
               'device_read': bool(snapshot), 'transport': 'Bluetooth' if snapshot.get('port','').startswith('ble:') else 'USB' if snapshot else None,
               'supported_settings': sorted(set(snapshot.get('settings', {})) & set(FIELDS)),
               'reported_channel_count': len(snapshot.get('channels', [])),
               'max_channels': device.get('max_channels') if type(device.get('max_channels')) is int else None,
               'firmware': device.get('ver') if isinstance(device.get('ver'),str) and __import__('re').fullmatch(r'v?[0-9]+[.][0-9]+[.][0-9]+(?:-[a-fA-F0-9]+)?',device['ver']) else None,
               'board_family': next((v for v in ('T114','T1000','T-Echo','RAK4631','Heltec') if v.lower() in str(device.get('model','')).lower()), 'Other / not reported'),
               'protocol_version': device.get('fw ver') if type(device.get('fw ver')) is int else None,
               'optional_read_error_count': len(snapshot.get('read_errors', {})),
               'legacy_startup_log_present': (folder/'startup-error.log').exists(),
               'update_log_present': (folder/'Updates'/'update.log').exists(),
               'update_installed': (folder/'Updates'/'update.log').exists() and (folder/'Updates'/'update.log').read_text(encoding='utf-8',errors='replace').strip() == 'Update installed.',
               'privacy': 'No names, identifiers, locations, keys, contacts, settings values, file paths, exception messages or raw logs included.'}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('summary.json', json.dumps(summary, indent=2))
        z.writestr('errors.json', json.dumps(events[-300:], indent=2))
    return len(events[-300:])


def issue_url():
    from urllib.parse import urlencode
    body = ('App version: ' + VERSION + '\n\nWhat happened?\n\nSteps to reproduce:\n1. \n\nExpected result:\n\nAttach the MeshCore-support.zip here by dragging it into this description. '
            'Please review screenshots for names, locations, channel keys or other private information before attaching them.')
    return 'https://github.com/TheIlluminate92/meshcore-configurator/issues/new?' + urlencode({'title':'Bug report — '+VERSION,'body':body})
