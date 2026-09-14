import unittest
import json, tempfile
from pathlib import Path
from radio_extras import discovered_settings, format_diagnostics
from model import validate, profile, load_document

class EverydayTests(unittest.TestCase):
    def test_requires_exact_advertisement(self):
        self.assertEqual(discovered_settings({'screen_timeout': '15'}), {})
        for schema in ('2', None):
            self.assertEqual(discovered_settings(dict(ui_schema=schema, screen_min='5', screen_max='300', screen_timeout='15')), {})

    def test_supported_only_and_ranges(self):
        caps = dict(ui_schema='1', screen_min='5', screen_max='300', screen_timeout='15', screen_usb='0', usb_priority='1')
        self.assertEqual(discovered_settings(caps), dict(screen_timeout=15, screen_usb=0, usb_priority=1))
        caps['screen_timeout']='0'; caps['screen_usb']='2'
        self.assertEqual(discovered_settings(caps), {'usb_priority': 1})
        caps['screen_max']='999'; self.assertEqual(discovered_settings(caps), {})

    def test_profile_roundtrip(self):
        values = dict(screen_timeout=30, screen_usb=1, usb_priority=0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'profile.json'
            path.write_text(json.dumps(profile(values)), encoding='utf-8')
            self.assertEqual(load_document(path)[0], values)
        for value in (-1,0,4,301,'15x'):
            with self.assertRaises(ValueError): validate({'screen_timeout': value})

    def test_diagnostics_missing_values(self):
        text = format_diagnostics(dict(port='mock', captured_at='now', core={'battery_mv': 4000}, errors={'radio': 'unsupported'}))
        self.assertIn('4000', text); self.assertIn('Not reported', text); self.assertIn('unsupported', text)



class EverydayApplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_and_verify_and_mismatch(self):
        import copy, tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        import device
        from test_configurator import BASE
        for mismatch in (False, True):
            state = copy.deepcopy(BASE)
            state['settings'].update(screen_timeout=15, screen_usb=0, usb_priority=0)
            baseline = copy.deepcopy(state)
            sent = []
            async def basic(*args): return copy.deepcopy(state)
            async def custom(key, value):
                sent.append((key, value))
                if not mismatch: state['settings'][key] = int(value)
                return SimpleNamespace(type=SimpleNamespace(name='OK'),payload={})
            async def operate(port, action):
                return await action(SimpleNamespace(commands=SimpleNamespace(set_custom_var=custom)))
            with tempfile.TemporaryDirectory() as folder, patch.object(device,'basic',basic), patch.object(device,'operate',operate):
                if mismatch:
                    with self.assertRaisesRegex(RuntimeError, 'Read-back mismatch'):
                        await device.apply_device('mock',baseline,dict(screen_timeout=30,screen_usb=1,usb_priority=1),folder)
                else:
                    result = await device.apply_device('mock',baseline,dict(screen_timeout=30,screen_usb=1,usb_priority=1),folder)
                    self.assertEqual(result['settings']['screen_timeout'],30)
            self.assertEqual(sent,[('screen_timeout','30'),('screen_usb','1'),('usb_priority','1')])

    async def test_diagnostics_partial_support(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from radio_extras import read_diagnostics
        import device
        calls=[]
        async def core():
            calls.append('core');return SimpleNamespace(type=SimpleNamespace(name='STATS_CORE'),payload={'battery_mv':4100})
        async def unsupported():
            calls.append('unsupported');return SimpleNamespace(type=SimpleNamespace(name='ERROR'),payload={})
        async def operate(port, action):
            return await action(SimpleNamespace(commands=SimpleNamespace(get_stats_core=core,get_stats_radio=unsupported,get_stats_packets=unsupported)))
        with patch.object(device,'operate',operate): result=await read_diagnostics('mock')
        self.assertEqual(result['core']['battery_mv'],4100)
        self.assertEqual(set(result['errors']),{'radio','packets'})
        self.assertEqual(len(calls),3)

if __name__ == '__main__': unittest.main()
