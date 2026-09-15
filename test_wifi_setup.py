import asyncio
import base64
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from wifi_setup import encode_setup, decode_status, endpoint, configure


class WiFiSetupTests(unittest.TestCase):
    def test_tuning_preserves_partner_and_checks_readback(self):
        import copy, tempfile, device
        from test_configurator import BASE
        for mismatch in (False, True):
            state=copy.deepcopy(BASE)
            state['settings'].update(rx_delay=0.0,airtime_factor=1.0)
            before=copy.deepcopy(state); calls=[]
            async def basic(*args): return copy.deepcopy(state)
            async def tuning(rx,af):
                calls.append((rx,af))
                if not mismatch: state['settings'].update(rx_delay=rx/1000,airtime_factor=af/1000)
                return SimpleNamespace(type=SimpleNamespace(name='OK'),payload={})
            async def operate(port,action): return await action(SimpleNamespace(commands=SimpleNamespace(set_tuning=tuning)))
            with tempfile.TemporaryDirectory() as directory,patch.object(device,'basic',basic),patch.object(device,'operate',operate):
                if mismatch:
                    with self.assertRaisesRegex(RuntimeError,'Read-back mismatch'):
                        asyncio.run(device.apply_device('mock',before,{'rx_delay':2.125},directory))
                else:
                    result=asyncio.run(device.apply_device('mock',before,{'rx_delay':2.125},directory))
                    self.assertEqual(result['settings']['airtime_factor'],1)
            self.assertEqual(calls,[(2125,1000)])

    def test_wire_boundaries_and_secret_not_in_status(self):
        wire=base64.b64decode(encode_setup(True,'s'*32,'p'*63,65535))
        self.assertEqual(len(wire),100)
        self.assertEqual(wire[:5],bytes([1,255,255,32,63]))
        self.assertEqual(len(encode_setup(True,'s'*32,'p'*63,65535)),136)
        self.assertEqual(decode_status(dict(wifi_schema='1',wifi_on='0',wifi_port='5000',wifi_ssid=''))['ssid'],'')
        for args in [(True,'s'*33,'',5000),(True,'s','short',5000),(True,'','',5000),(True,'a\0b','',5000),(True,'s','',0),(True,'s','',65536)]:
            with self.assertRaises(ValueError): encode_setup(*args)

    def test_endpoints(self):
        self.assertEqual(endpoint('192.168.1.5'),('192.168.1.5',5000))
        self.assertEqual(endpoint('tcp://radio.local:1234'),('radio.local',1234))
        self.assertEqual(endpoint('[::1]:5000'),('::1',5000))
        for value in ['https://radio','tcp://user:secret@radio','radio:65536','radio/path','bad host','radio:0']:
            with self.assertRaises(ValueError): endpoint(value)

    def test_rejects_unknown_schema_and_network_provisioning(self):
        with self.assertRaises(ValueError): decode_status({'wifi_schema':'2'})
        with self.assertRaises(ValueError): asyncio.run(configure('tcp://radio:5000','id',True,'s','password',5000))

    def test_identity_guard_and_readback(self):
        import device
        custom=dict(wifi_schema='1',wifi_on='0',wifi_port='5000',wifi_ssid='')
        sent=[]
        def reply(name,payload): return SimpleNamespace(type=SimpleNamespace(name=name),payload=payload)
        async def basic(*args): return {'self_info':{'public_key':'id'},'custom_vars':custom.copy()}
        async def set_var(key,value):
            sent.append(key); custom.update(wifi_on='1',wifi_ssid='73736964')
            return reply('OK',{})
        async def get_vars(): return reply('CUSTOM_VARS',custom.copy())
        async def operate(port,action): return await action(SimpleNamespace(commands=SimpleNamespace(set_custom_var=set_var,get_custom_vars=get_vars)))
        with patch.object(device,'basic',basic),patch.object(device,'operate',operate):
            with self.assertRaises(ValueError): asyncio.run(configure('COM1','wrong',True,'ssid','password',5000))
            self.assertEqual(sent,[])
            result=asyncio.run(configure('COM1','id',True,'ssid','password',5000))
            self.assertTrue(result['enabled']); self.assertNotIn('password',result)
            with self.assertRaises(RuntimeError): asyncio.run(configure('COM1','id',True,'different','password',5000))
