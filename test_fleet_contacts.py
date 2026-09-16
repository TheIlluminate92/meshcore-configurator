import asyncio
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import device
from fleet_contacts import FleetContactStore, card_bytes, contact_rows, export_contact_list

KEY_A = 'aa' * 32
KEY_B = 'bb' * 32
KEY_C = 'cc' * 32
def card(key, app=b'\x01'):
    # Flood advert, empty path, public key, timestamp, signature and app byte.
    return 'meshcore://' + (bytes([0x11, 0])+bytes.fromhex(key)+bytes(4)+bytes(64)+app).hex()
URI_A = card(KEY_A)
URI_B = card(KEY_B)


def snapshot(key=KEY_A, name='Alpha', contacts=None):
    return {'port': 'COM4', 'device': {'model': 'T1000-E', 'ver': '1.17.1', 'max_contacts': 10},
            'self_info': {'public_key': key, 'max_tx_power': 22},
            'settings': {'name': name}, 'contacts': contacts or {}, 'self_contact_uri': URI_A}


class FleetLibraryTests(unittest.TestCase):
    def test_remember_updates_card_and_preserves_first_seen(self):
        with tempfile.TemporaryDirectory() as folder:
            store = FleetContactStore(Path(folder) / 'fleet.json')
            self.assertTrue(store.remember(snapshot()))
            first = store.entries()[0]['first_seen']
            changed = snapshot(name='Alpha 2'); changed['self_contact_uri'] = card(KEY_A,b'\x02')
            store.remember(changed)
            entry = store.entries()[0]
            self.assertEqual(entry['name'], 'Alpha 2')
            self.assertEqual(entry['contact_uri'], card(KEY_A,b'\x02'))
            self.assertEqual(entry['first_seen'], first)

    def test_missing_card_is_not_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            store = FleetContactStore(Path(folder) / 'fleet.json')
            item = snapshot(); item.pop('self_contact_uri')
            self.assertFalse(store.remember(item))
            self.assertEqual(store.entries(), [])

    def test_card_validation(self):
        self.assertEqual(card_bytes(URI_A), bytes.fromhex(URI_A.split('://')[1]))
        for value in ('http://bad', 'meshcore://x', 'meshcore://'):
            with self.subTest(value=value), self.assertRaises(ValueError): card_bytes(value)

    def test_mismatched_card_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=FleetContactStore(Path(folder)/'fleet.json')
            item=snapshot();item['self_contact_uri']=URI_B
            with self.assertRaisesRegex(ValueError,'does not match'):store.remember(item)

    def test_exports_csv_and_json(self):
        contacts={KEY_B:{'public_key':KEY_B,'adv_name':'Bravo','type':1,'adv_lat':1.2,'adv_lon':3.4}}
        item=snapshot(contacts=contacts)
        with tempfile.TemporaryDirectory() as folder:
            csv_path=Path(folder)/'contacts.csv';json_path=Path(folder)/'contacts.json'
            self.assertEqual(export_contact_list(csv_path,item),1)
            self.assertEqual(export_contact_list(json_path,item),1)
            with csv_path.open(encoding='utf-8-sig') as stream:self.assertEqual(list(csv.DictReader(stream))[0]['adv_name'],'Bravo')
            self.assertEqual(json.loads(json_path.read_text())['contacts'][0]['public_key'],KEY_B)

    def test_export_requires_successful_contact_read(self):
        item=snapshot();item.pop('contacts')
        with tempfile.TemporaryDirectory() as folder,self.assertRaisesRegex(ValueError,'did not return'):
            export_contact_list(Path(folder)/'contacts.csv',item)


class ContactWriteTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, entries, *, current_contacts=None, maximum=10, wrong=False):
        current=snapshot(KEY_C if wrong else KEY_A, contacts=current_contacts)
        current['device']['max_contacts']=maximum
        contacts=copy.deepcopy(current_contacts or {})
        imported=[]
        async def get_contacts():return SimpleNamespace(type=SimpleNamespace(name='CONTACTS'),payload=copy.deepcopy(contacts))
        async def import_contact(raw):
            imported.append(raw)
            record=next(e for e in entries if card_bytes(e['contact_uri'])==raw)
            contacts[record['public_key']]={'public_key':record['public_key'],'adv_name':record['name']}
            return SimpleNamespace(type=SimpleNamespace(name='OK'),payload={})
        mc=SimpleNamespace(commands=SimpleNamespace(get_contacts=get_contacts,import_contact=import_contact))
        async def operate(port,action):return await action(mc)
        async def basic(*args):return copy.deepcopy(current)
        with tempfile.TemporaryDirectory() as folder,patch.object(device,'operate',operate),patch.object(device,'basic',basic):
            result=await device.add_contacts('COM4',snapshot(),entries,folder)
            reports=[json.loads(p.read_text()) for p in Path(folder).glob('contacts-*.json')]
        return result,imported,reports

    async def test_add_skip_self_existing_and_verify(self):
        entries=[{'public_key':KEY_A,'name':'Alpha','contact_uri':URI_A},
                 {'public_key':KEY_B,'name':'Bravo','contact_uri':URI_B}]
        result,imported,reports=await self.exercise(entries)
        self.assertEqual(imported,[card_bytes(URI_B)])
        self.assertEqual((result['added'],result['skipped']),(1,1))
        self.assertTrue(reports[0]['verified'])

    async def test_capacity_blocks_before_write(self):
        entries=[{'public_key':KEY_B,'name':'Bravo','contact_uri':URI_B}]
        with self.assertRaises(ValueError):await self.exercise(entries,maximum=0)

    async def test_wrong_target_blocks_before_write(self):
        entries=[{'public_key':KEY_B,'name':'Bravo','contact_uri':URI_B}]
        with self.assertRaises(ValueError):await self.exercise(entries,wrong=True)

    async def test_manual_filters_temporarily_enable_type_and_restore(self):
        entries=[{'public_key':KEY_B,'name':'Bravo','contact_uri':URI_B}]
        current=snapshot();current['self_info']['manual_add_contacts']=True
        current['auto_add']={'config':4,'max_hops':6}  # repeaters only
        contacts={};pending=[];reads_after_import=0;flags=4;flag_writes=[]
        async def get_contacts():
            nonlocal reads_after_import
            if pending:
                reads_after_import+=1
                if reads_after_import>=2 and flags&2:
                    key=pending.pop();contacts[key]={'public_key':key,'adv_name':'Bravo'}
            return SimpleNamespace(type=SimpleNamespace(name='CONTACTS'),payload=copy.deepcopy(contacts))
        async def import_contact(raw):
            pending.append(KEY_B)
            return SimpleNamespace(type=SimpleNamespace(name='OK'),payload={})
        async def send(packet,expected):
            nonlocal flags
            self.assertEqual(packet[0],58);flags=packet[1];flag_writes.append(flags)
            return SimpleNamespace(type=SimpleNamespace(name='OK'),payload={})
        async def get_autoadd_config():
            return SimpleNamespace(type=SimpleNamespace(name='AUTOADD_CONFIG'),payload={'config':flags,'max_hops':6})
        mc=SimpleNamespace(commands=SimpleNamespace(get_contacts=get_contacts,import_contact=import_contact,
                            send=send,get_autoadd_config=get_autoadd_config))
        async def operate(port,action):return await action(mc)
        async def basic(*args):return copy.deepcopy(current)
        with tempfile.TemporaryDirectory() as folder,patch.object(device,'operate',operate),patch.object(device,'basic',basic):
            result=await device.add_contacts('COM4',snapshot(),entries,folder)
            report=json.loads(next(Path(folder).glob('contacts-*.json')).read_text())
        self.assertEqual(flag_writes,[6,4])
        self.assertEqual(result['added'],1)
        self.assertTrue(report['discovery_restored'])
        self.assertEqual(report['verified_contacts'][0]['public_key'],KEY_B)


if __name__ == '__main__': unittest.main()
