import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from restore import restore_document, backups
from diagnostics import record_error, support_report
from compatibility import review
from builtin_profiles import entries
from model import load_document, profile
from batch import plan_device
from test_profiles_batch import radio

class RestoreTests(unittest.TestCase):
    def report(self):
        return {'before':radio(), 'requested':{'tx_power':14}, 'channels_before':radio()['channels'],
                'channels_requested':[{'index':0,'name':'Changed','secret':'22'*16}], 'verified':False}

    def test_only_changed_values_restored_even_after_failed_write(self):
        s=radio();s['settings']['tx_power']=14;s['settings']['name']='New name'
        d=restore_document(self.report(),s)
        self.assertEqual(d['settings'],{'tx_power':22})
        self.assertEqual(d['channels'],radio()['channels'])
        self.assertNotIn('name',d['settings'])

    def test_identity_and_missing_backup_blocks(self):
        with self.assertRaisesRegex(ValueError,'different radio'):restore_document(self.report(),radio(identity='other'))
        r=self.report();r['channels_before']=[]
        with self.assertRaisesRegex(ValueError,'missing original channel'):restore_document(r,radio())
        r=self.report();r['requested']['gps']=1
        with self.assertRaisesRegex(ValueError,'missing original values'):restore_document(r,radio())

    def test_new_power_limit_blocks_restore(self):
        s=radio();s['self_info']['max_tx_power']=14
        with self.assertRaises(ValueError):restore_document(self.report(),s)

    def test_reports_filtered_by_identity_and_damage_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'apply-good.json').write_text(json.dumps(self.report()))
            (p/'apply-bad.json').write_text('{')
            self.assertEqual(len(backups(p,'one')[0]),1)
            self.assertEqual(backups(p,'other'),([],1))
            self.assertTrue((p/'apply-bad.json').exists())

class SupportTests(unittest.TestCase):
    def test_github_issue_link_contains_no_local_data(self):
        from diagnostics import issue_url
        from urllib.parse import urlparse, parse_qs
        u=urlparse(issue_url())
        self.assertEqual(u.netloc,'github.com')
        self.assertEqual(u.path,'/TheIlluminate92/meshcore-configurator/issues/new')
        self.assertIn('MeshCore-support.zip',parse_qs(u.query)['body'][0])


    def test_secrets_and_names_never_in_log_or_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            try:raise RuntimeError('secret-user-location-key-password')
            except RuntimeError as exc:record_error('device',exc,p)
            s=radio();s['settings']['name']='PRIVATE-NAME';s['self_info']['public_key']='PRIVATE-ID'
            s['read_errors']={'PRIVATE-ERROR':'PRIVATE-PAYLOAD'}
            (p/'startup-error.log').write_text('PRIVATE-TRACEBACK')
            count=support_report(p/'report.zip',s,p)
            self.assertEqual(count,1)
            with zipfile.ZipFile(p/'report.zip') as z:
                all_text=''.join(z.read(n).decode() for n in z.namelist())
                summary=json.loads(z.read('summary.json'))
            self.assertTrue(summary['legacy_startup_log_present'])
            self.assertNotIn('PRIVATE',all_text)
            self.assertNotIn('secret-user',all_text)
            self.assertNotIn('secret-user',(p/'logs'/'errors.jsonl').read_text())
            self.assertNotIn('11'*16,all_text)

    def test_no_radio_and_malformed_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'logs').mkdir();(p/'logs'/'errors.jsonl').write_text('bad\n'+json.dumps({'context':'private','kind':'private','frames':[]}))
            self.assertEqual(support_report(p/'r.zip',folder=p),1)
            with zipfile.ZipFile(p/'r.zip') as z:self.assertFalse(json.loads(z.read('summary.json'))['device_read'])

class CompatibilityDefaultsTests(unittest.TestCase):
    def test_mixed_hardware_review_reports_each_block(self):
        s=radio();s['self_info']['max_tx_power']=14
        rows,blocked=review(s,{'settings':{'gps_interval':60,'tx_power':22},'channels':[{'index':5,'name':'x','secret':'11'*16}]})
        self.assertTrue(blocked)
        self.assertEqual(len(rows),3)
        self.assertTrue(all('Blocked' in r[1] for r in rows))

    def test_defaults_do_not_override_network_or_identity(self):
        a=entries();self.assertEqual(len(a),3)
        for d in a:
            self.assertFalse(set(d['settings']) & {'name','frequency','bandwidth','spreading_factor','coding_rate','tx_power','latitude','longitude'})
            self.assertFalse(d['channels'])
        a[0]['settings']['multi_acks']=3
        self.assertEqual(entries()[0]['settings']['multi_acks'],0)

    def test_server_profiles_never_enter_companion_write_or_import(self):
        for d in entries()[1:]:
            with self.assertRaisesRegex(ValueError,'Companion firmware only'):plan_device(radio(),d)
            with tempfile.TemporaryDirectory() as tmp:
                data=profile({},[]);data['target_role']=d['target_role']
                p=Path(tmp)/'p.json';p.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'Companion firmware only'):load_document(p)


class RestoreUITests(unittest.TestCase):
    def test_restore_rereads_and_loads_editor_without_writing(self):
        import tkinter as tk
        import asyncio
        from unittest.mock import patch, AsyncMock
        import app
        from restore_ui import open_restore
        with tempfile.TemporaryDirectory() as tmp, patch.object(app,'ROOT',Path(tmp)), patch.object(app,'serial_ports',return_value=[]):
            root=tk.Tk();root.withdraw();a=app.App(root)
            try:
                s=radio();s['settings']['tx_power']=14
                a.port.set('COM4');a.show(s)
                folder=Path(tmp)/'reports';folder.mkdir()
                (folder/'apply-test.json').write_text(json.dumps(RestoreTests().report()))
                def run(operation, callback, label):callback(asyncio.run(operation))
                with patch.object(a,'run',side_effect=run), patch('restore_ui.read_device',AsyncMock(return_value=s)) as read, patch('app.apply_device') as write:
                    open_restore(a,folder);root.update()
                    def walk(w):
                        for child in w.winfo_children():
                            yield child
                            yield from walk(child)
                    button=next(w for w in walk(root) if w.winfo_class()=='TButton' and w.cget('text')=='Reread & load previous values')
                    button.invoke();root.update()
                    read.assert_awaited_once_with('COM4');write.assert_not_called()
                    self.assertEqual(a.variables['tx_power'].get(),'22')
                    self.assertEqual(a.snapshot['settings']['tx_power'],14)
            finally:
                a.pending_count=0;a.close()
