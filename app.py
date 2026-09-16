"""Desktop entry point. All serial work runs off the Tk event loop."""
import asyncio
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
from setting_box import SettingBox
from model import FIELDS, CHOICES, OTHER, AUTO, validate, validate_channels, load_document, profile, changes, display, parse_input
from device import bluetooth_devices, serial_ports, read_device, apply_device, save_json
from help_text import HELP
from tooltips import Tooltip, help_label
from theme import apply_theme
from guidance import BatteryHint

from diagnostics import record_error
from app_paths import DATA_ROOT
ROOT = DATA_ROOT

class App:
    def __init__(self, root):
        self.root, self.snapshot, self.busy = root, None, False
        root.report_callback_exception = self.callback_error
        self.loading = False
        self.pending_count = 0
        self.editor_port_choice = ''
        self.editor_transport = 'USB'
        self.batch_window = None
        self.update_window = None
        self.theme_job = None
        self.closing = False
        from history_store import HistoryStore
        self.history = HistoryStore(ROOT / 'data' / 'history.sqlite3')
        from fleet_contacts import FleetContactStore
        self.fleet_contacts = FleetContactStore(ROOT / 'data' / 'fleet_contacts.json')
        self.pending = tk.StringVar(value='Read a radio to begin')
        self.support_summary = tk.StringVar(value='USB COMPANION  /  LOCAL CONFIGURATION')
        self.results = queue.Queue()
        root.title('MeshCore Configurator — USB, Bluetooth & Wi-Fi')
        root.geometry('1180x820')
        root.minsize(1100, 800)
        from preferences import load_preferences
        self.preferences=load_preferences(ROOT/'preferences.json')
        if self.preferences.get('geometry'):
            import re
            w,h,x,y=map(int,re.findall(r'\d+',self.preferences['geometry']))
            root.geometry(f'{min(w,max(1100,root.winfo_screenwidth()))}x{min(h,max(800,root.winfo_screenheight()-60))}+{min(x,max(0,root.winfo_screenwidth()-1100))}+{min(y,max(0,root.winfo_screenheight()-800))}')
        apply_theme(root,self.preferences.get('theme','System'))
        outer = ttk.Frame(root, padding=12, style='Root.TFrame')
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer, padding=(20, 10), style='Header.TFrame')
        header.pack(fill='x', pady=(0, 10))
        tools_button=ttk.Menubutton(header,text='Help');tools_button.pack(side='right',padx=(8,0))
        tools_menu=tk.Menu(tools_button,tearoff=False);tools_button.configure(menu=tools_menu)
        tools_menu.add_command(label='Save support report…',command=self.save_support)
        tools_menu.add_command(label='Report a bug on GitHub…',command=lambda:self.save_support(open_github=True))
        tools_menu.add_separator()
        tools_menu.add_command(label='Detect firmware role…',command=self.detect_firmware)
        tools_menu.add_command(label='Radio diagnostics…',command=self.radio_diagnostics)
        tools_menu.add_command(label='Export dry run…',command=self.export_dry_run)
        tools_menu.add_command(label='Back up portable app…',command=self.backup_portable)
        ttk.Button(header,text='App updates',command=self.open_updates).pack(side='right',padx=(8,0))
        from wifi_setup import open_setup
        ttk.Button(header,text='Wi-Fi setup',command=lambda:open_setup(self)).pack(side='right',padx=(8,0))
        self.theme_choice=tk.StringVar(value=self.preferences.get('theme','System'))
        theme_box=ttk.Combobox(header,textvariable=self.theme_choice,values=['Light','Dark','System'],state='readonly',width=8)
        theme_box.pack(side='right')
        theme_box.bind('<<ComboboxSelected>>',lambda _:self.change_theme())
        ttk.Label(header, text='MeshCore  /  Device Configurator', style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, text='01  Connect & read     →     02  Edit profile     →     03  Review & verify', style='Subtitle.TLabel').pack(anchor='w', pady=(8, 0))
        connection = ttk.Frame(outer, padding=(18, 12))
        connection.pack(fill='x', pady=(0, 10))
        row = ttk.Frame(connection)
        row.pack(fill='x')
        self.transport = tk.StringVar(value='USB')
        self.transport_box = ttk.Combobox(row, textvariable=self.transport, values=['USB', 'Bluetooth', 'Wi-Fi'], width=12, state='readonly')
        self.transport_box.pack(side='left', padx=(0, 8))
        self.transport_box.bind('<<ComboboxSelected>>', lambda _: self.change_transport())
        self.port = tk.StringVar()
        self.port_box = ttk.Combobox(row, textvariable=self.port, width=43, state='readonly')
        self.port_box.pack(side='left')
        Tooltip(self.port_box, 'USB serial port', HELP['port'])
        help_label(row, '?', 'Bluetooth needs BLE-enabled Companion firmware. Windows handles pairing. Close phone/browser connections before reading.').pack(side='left')
        self.port_box.bind('<<ComboboxSelected>>', lambda _: self.choose_port())
        self.buttons = []
        self.action_buttons = {}
        self.button(row, 'Find devices', self.scan)
        self.button(row, 'Read device', self.read)
        self.button(row, 'Batch editor', self.open_batch)
        self.identity = tk.StringVar(value='No device read. Connect a Companion USB device, then select its port.')
        ttk.Label(connection, textvariable=self.identity, wraplength=1030, style='Muted.TLabel').pack(anchor='w', pady=(10, 4))
        ttk.Label(connection, textvariable=self.support_summary, style='Caption.TLabel').pack(anchor='w')
        footer = ttk.Frame(outer, style='Root.TFrame')
        footer.pack(side='bottom', fill='x')
        notebook = ttk.Notebook(outer)
        notebook.pack(fill='both', expand=True)
        self.variables, self.entries, self.current = {}, {}, {}
        self.hints = {}
        groups = {
            'Device & radio': ('name', 'frequency', 'bandwidth', 'spreading_factor', 'coding_rate', 'tx_power', 'path_hash_mode', 'multi_acks'),
            'Location & GPS': ('gps', 'motion_gps', 'gps_interval', 'latitude', 'longitude', 'advert_location_policy'),
            'Contact discovery': ('manual_add_contacts',) + AUTO,
            'Telemetry': ('telemetry_mode_base', 'telemetry_mode_loc', 'telemetry_mode_env'),
            'Advanced': ('rx_delay', 'airtime_factor'),
            'Device options': ('buzzer_quiet', 'led_mode', 'screen_timeout', 'screen_usb', 'usb_priority'),
        }
        notes = {
            'Advanced': 'Leave these at the firmware defaults unless testing a specific network requirement. Both values are read and written together, rounded to 0.001. Receive delay: 0–20; airtime factor: 0–9. These match the firmware limits applied on reboot.',
            'Device options': 'Available only when reported by compatible firmware. USB priority pauses BLE commands while a USB app has the port open; unplugging restores access. Screen timeout applies on the next wake or interaction.',
            'Device & radio': 'Choose US/Canada or EU/UK frequency suggestions, or type a custom MHz value. Frequency selection changes frequency only; bandwidth, spreading factor and coding rate must also match your network. Bandwidth accepts dropdown choices or custom kHz values. Repeat mode is preserved.',
            'Location & GPS': 'Fixed coordinates require GPS to be off. GPS options depend on the hardware and firmware. Location sharing in adverts and telemetry access are separate settings.',
            'Contact discovery': '“Automatically add all types” overrides the individual type filters. Use selected types/manual mode to apply them. With all type filters off, contacts are added manually. The hop limit still applies.',
            'Telemetry': 'Device telemetry access must allow a requester before location or environment telemetry can be returned. “Allowed contacts only” uses each contact’s permission flags. Location in adverts is controlled separately.',
        }
        for title, keys in groups.items():
            editor = ttk.Frame(notebook, padding=12)
            notebook.add(editor, text=title)
            for column, label in enumerate(('Setting', 'Device value', 'Profile value', 'Suggestion')):
                heading = ttk.Label(editor, text=label.upper(), style='Caption.TLabel')
                heading.grid(row=0, column=column, sticky='w', padx=(0, 12), pady=(0, 8))
                if column in (1, 2):
                    Tooltip(heading, label, HELP['device_value' if column == 1 else 'profile_value'])
            for index, key in enumerate(keys, 1):
                caption = help_label(editor, FIELDS[key][0], HELP[key])
                caption.winfo_children()[0].configure(width=1)
                caption.winfo_children()[0].pack_configure(fill='x', expand=True)
                caption.grid(row=index, column=0, sticky='ew', padx=(0, 12), pady=3)
                caption.bind('<Configure>', lambda e, label=caption.winfo_children()[0]: label.configure(wraplength=max(100, e.width-35)))
                current = tk.StringVar(value='Not read')
                value_label = ttk.Label(editor, textvariable=current, width=1, wraplength=220, style='Muted.TLabel')
                value_label.grid(row=index, column=1, sticky='ew', padx=(0, 12))
                value_label.bind('<Configure>', lambda e, label=value_label: label.configure(wraplength=max(100, e.width)))
                variable = tk.StringVar()
                if key in CHOICES:
                    entry = SettingBox(editor, textvariable=variable, values=list(CHOICES[key].values()), width=18, state='disabled')
                else:
                    entry = ttk.Entry(editor, textvariable=variable, width=18, state='disabled')
                entry.grid(row=index, column=2, sticky='ew', padx=(0, 12))
                self.hints[key] = BatteryHint(editor, key, roomy=True)
                self.hints[key].grid(row=index, column=3, sticky='ew', padx=(0, 0), pady=1)
                Tooltip(entry, FIELDS[key][0], HELP[key])
                self.variables[key], self.entries[key], self.current[key] = variable, entry, current
                variable.trace_add('write', lambda *_, k=key: self.edited())
            for column in range(4):
                editor.columnconfigure(column, weight=1, uniform='settings')
            ttk.Label(editor, text=notes[title], wraplength=1020, style='Note.TLabel').grid(row=len(keys)+1, column=0, columnspan=4, sticky='w', pady=4)
        self.channel_page = ttk.Frame(notebook, padding=12)
        notebook.add(self.channel_page, text='Channels')
        ttk.Label(self.channel_page, text='Existing channels stay visible. Choose how many empty slots to add. Reducing this number does not delete channels or edits.\nClear a slot explicitly with an empty name and a zero key; writes still require Review & apply.', wraplength=1050).pack(anchor='w', pady=(0, 8))
        channel_tools = ttk.Frame(self.channel_page)
        channel_tools.pack(fill='x', pady=(0, 8))
        ttk.Label(channel_tools, text='Empty slots to add:').pack(side='left')
        self.channel_count = tk.StringVar(value='0')
        self.channel_count_box = ttk.Spinbox(channel_tools, from_=0, to=0, textvariable=self.channel_count, width=4)
        self.channel_count_box.pack(side='left', padx=8)
        self.channel_limit = tk.StringVar(value='Read a device to see its channel limit.')
        ttk.Label(channel_tools, textvariable=self.channel_limit, style='Muted.TLabel').pack(side='left')
        self.channel_canvas = tk.Canvas(self.channel_page, highlightthickness=0, background='white')
        scrollbar = ttk.Scrollbar(self.channel_page, orient='vertical', command=self.channel_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.channel_canvas.pack(fill='both', expand=True)
        self.channel_canvas.configure(yscrollcommand=scrollbar.set)
        self.channel_rows = ttk.Frame(self.channel_canvas)
        window = self.channel_canvas.create_window((0, 0), window=self.channel_rows, anchor='nw')
        self.channel_canvas.bind('<Configure>', lambda e: self.channel_canvas.itemconfigure(window, width=e.width))
        self.channel_rows.bind('<Configure>', lambda e: self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox('all')))
        self.channel_vars, self.channel_entries = {}, []
        self.channel_widgets = {}
        self.channel_count.trace_add('write', lambda *_: self.filter_channels())
        self.variables['gps'].trace_add('write', lambda *_: self.location_state())
        self.details = tk.Text(notebook, wrap='none', font=('Consolas', 10), background='#f8fafc', foreground='#243c53', relief='flat', padx=16, pady=16)
        notebook.add(self.details, text='Device data')
        from contact_ui import ContactPage
        self.contact_page = ContactPage(notebook, self)
        notebook.add(self.contact_page.frame, text='Contacts')
        from library_ui import LibraryPage
        self.profile_page = LibraryPage(notebook, self, ROOT / 'profiles')
        notebook.add(self.profile_page, text='Saved profiles')
        from history_ui import HistoryPage
        self.history_page = HistoryPage(notebook,self)
        notebook.add(self.history_page,text='History')
        ttk.Label(footer, text='Battery icons appear where useful: more filled = higher drain. Rough guidance, not runtime. Radio costs apply during transmission.', style='Status.TLabel', wraplength=1040).pack(anchor='w', pady=(5, 0))
        ttk.Label(footer, textvariable=self.pending, style='Pending.TLabel').pack(anchor='w', pady=(13, 0))
        actions = ttk.Frame(footer, style='Root.TFrame')
        actions.pack(fill='x', pady=10)
        self.button(actions, 'Load JSON profile', self.load)
        self.button(actions, 'Save JSON profile', self.save)
        self.button(actions, 'Save device snapshot', self.save_snapshot)
        self.button(actions, 'Review & apply', self.apply)
        self.status = tk.StringVar(value='Ready. No configuration has been written.')
        self.state_badge=tk.StringVar(value='○ Ready')
        ttk.Label(row,textvariable=self.state_badge,style='Muted.TLabel').pack(side='right',padx=8)
        self.status.trace_add('write',lambda *_:self.refresh_state_badge())
        ttk.Label(footer, textvariable=self.status, wraplength=1010, style='Status.TLabel').pack(anchor='w')
        root.bind('<Map>',lambda event:self.theme_new_window(event),add='+')
        self.queue_theme()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_id = root.after(100, self.poll)
        self.scan()
        self.edited()

    def radio_diagnostics(self):
        if self.busy or self.batch_window is not None or self.update_window is not None: return
        try: port = self.selected_port()
        except ValueError as exc:
            messagebox.showerror('Radio diagnostics', str(exc)); return
        from radio_extras import read_diagnostics, format_diagnostics
        def done(result):
            window = tk.Toplevel(self.root); window.title('Radio diagnostics')
            text = tk.Text(window, wrap='word', width=66, height=24, padx=16, pady=16)
            text.pack(fill='both', expand=True)
            text.insert('1.0', format_diagnostics(result)); text.configure(state='disabled')
            for key, entry in self.entries.items():
                entry.configure(state='normal' if self.snapshot and key in self.snapshot['settings'] else 'disabled')
            for entry in self.channel_entries: entry.configure(state='normal')
            self.edited(); self.location_state()
            self.status.set('Diagnostics complete. No settings changed; no background polling.')
        self.run(read_diagnostics(port), done, 'Reading local diagnostics…')

    def detect_firmware(self):
        if self.busy or self.batch_window is not None or self.update_window is not None:return
        if not self.confirm_discard():return
        try:port=self.selected_port()
        except ValueError as exc:messagebox.showerror('Firmware detection',str(exc));return
        self.invalidate()
        from firmware_role import detect,LABELS
        def done(role):
            self.identity.set(f'{LABELS[role]} | {port}')
            self.support_summary.set('ROLE DETECTION ONLY — READ DEVICE TO CONFIGURE' if role=='companion' else 'SERVER CONFIGURATION NOT YET SUPPORTED' if role in ('repeater','room') else 'NO RECOGNIZED FIRMWARE REPLY')
            self.status.set('Detected '+LABELS[role]+'. No settings changed.')
        self.run(detect(port),done,'Detecting firmware role from read-only protocol replies…')

    def export_dry_run(self):
        if self.busy or self.batch_window is not None:return
        try:
            data=profile(self.desired(),self.desired_channels())
            path=filedialog.asksaveasfilename(title='Save dry run (may contain names and locations)',defaultextension='.json',initialfile='MeshCore-dry-run.json',filetypes=[('Dry run JSON','*.json')])
            if path:
                from dry_run import export
                export(path,[self.snapshot],data)
                self.status.set('Dry run saved. No settings written; channel keys excluded.')
        except Exception as exc:messagebox.showerror('Dry run',str(exc),parent=self.root)

    def backup_portable(self):
        if self.busy or self.batch_window is not None or self.update_window is not None:
            messagebox.showinfo('Operation in progress','Close other app dialogs and wait for device operations to finish.');return
        path=filedialog.asksaveasfilename(title='Save private portable backup — keep this ZIP private',defaultextension='.zip',initialfile='MeshCore-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip',filetypes=[('Portable backup','*.zip')])
        if not path:return
        from portable_backup import create_backup
        import sys
        states=[(w,w.cget('state')) for w in list(self.entries.values())+self.channel_entries]
        async def work():
            try:return await asyncio.to_thread(create_backup,path,ROOT,sys.executable if getattr(sys,'frozen',False) else None),None
            except Exception as exc:
                record_error('interface',exc);return None,str(exc)
        def done(result):
            for w,state in states:w.configure(state=state)
            self.edited()
            count,error=result
            if error:
                self.status.set('Backup failed. Your editor and saved data are unchanged.')
                messagebox.showerror('Portable backup',error,parent=self.root)
            else:self.status.set(f'Backup verified and saved ({count} files). Contains private data; do not upload it as a support report.')
        self.run(work(),done,'Backing up portable data and history…')

    def callback_error(self, kind, value, trace):
        record_error('interface', value.with_traceback(trace))
        messagebox.showerror('Interface error', 'Something went wrong. A diagnostic entry was saved when possible. Use Help → Save support report.', parent=self.root)

    def save_support(self, open_github=False):
        if self.busy or (self.batch_window is not None and self.batch_window.busy):
            messagebox.showinfo('Operation in progress','Wait for the device operation to finish.');return
        path=filedialog.asksaveasfilename(title='Save private-data-free support report',defaultextension='.zip',initialfile='MeshCore-support.zip',filetypes=[('Support report','*.zip')])
        if not path:return
        try:
            from diagnostics import support_report
            count=support_report(path,self.snapshot,ROOT)
            self.status.set(f'Support report saved with {count} diagnostic entries. No names, keys, locations or raw device data included.')
            if open_github:
                import webbrowser
                from diagnostics import issue_url
                opened=webbrowser.open(issue_url())
                messagebox.showinfo('Attach your support report',f'Support ZIP saved:\n{path}\n\n'+('On the GitHub issue page, drag this ZIP into the description, describe what happened, and select Submit new issue. GitHub may ask you to sign in.' if opened else 'Open the project Issues page on GitHub, create a bug report, and attach this ZIP.')+'\n\nNothing has been uploaded or submitted automatically.',parent=self.root)
        except Exception as exc:
            record_error('support',exc)
            messagebox.showerror('Support report',str(exc),parent=self.root)

    def refresh_state_badge(self):
        value=self.status.get().lower()
        if any(word in value for word in ('failed','error','denied')):badge='! Needs attention'
        elif 'verified:' in value:badge='✓ Verified'
        elif self.busy:badge='↻ Working'
        elif self.snapshot:badge='✓ Read · ready to edit'
        else:badge='○ Ready'
        self.state_badge.set(badge)

    def theme_new_window(self,event):
        if isinstance(event.widget,tk.Toplevel):self.queue_theme()

    def queue_theme(self):
        if self.closing or self.theme_job is not None:return
        def refresh():
            self.theme_job=None
            if not self.closing:self.change_theme(save=False)
        self.theme_job=self.root.after_idle(refresh)

    def change_theme(self,save=True):
        apply_theme(self.root,self.theme_choice.get())
        if save:
            from preferences import save_preferences
            if not save_preferences(ROOT/'preferences.json',self.theme_choice.get(),self.root.geometry()) and hasattr(self,'status'):
                self.status.set('Appearance applied, but preferences could not be saved. Check folder access/free space.')

    def open_updates(self):
        if self.update_window is not None:
            self.update_window.window.lift();return
        if self.busy or (self.batch_window and self.batch_window.window.winfo_exists()):
            messagebox.showinfo('App updates','Finish the device operation and close the batch editor first.',parent=self.root);return
        from update_ui import UpdateWindow
        UpdateWindow(self)

    def button(self, frame, text, command):
        def guarded():
            try:
                command()
            except Exception as exc:
                record_error('interface',exc)
                messagebox.showerror('MeshCore Configurator', str(exc))
        b = ttk.Button(frame, text=text, command=guarded, style='Primary.TButton' if text in ('Read device', 'Review & apply') else 'TButton')
        b.pack(side='left', padx=(8, 0))
        self.buttons.append(b)
        self.action_buttons[text] = b
        if text in HELP:
            Tooltip(b, text, HELP[text])

    def open_batch(self):
        if not self.confirm_discard():return
        if self.snapshot is not None:self.show(self.snapshot)
        from batch_ui import BatchWindow
        BatchWindow(self)

    def confirm_discard(self):
        return not self.pending_count or messagebox.askyesno('Unsaved edits','The editor has pending changes. Continue without saving those edits?')

    def choose_port(self):
        if not self.confirm_discard():
            self.port.set(self.editor_port_choice);return
        self.invalidate()

    def change_transport(self):
        if not self.confirm_discard():
            self.transport.set(self.editor_transport);return
        self.port.set('')
        self.invalidate()
        self.scan()

    def scan(self):
        if self.transport.get() == 'Wi-Fi':
            from tkinter import simpledialog
            from wifi_setup import endpoint
            address = simpledialog.askstring('Connect over Wi-Fi','Radio IP address or hostname, optionally :5000',parent=self.root)
            if address:
                try:
                    host, number = endpoint(address)
                except ValueError as exc:
                    messagebox.showerror('Wi-Fi connection',str(exc)); return
                host = f'[{host}]' if ':' in host else host
                self.port.set(f'tcp://{host}:{number}')
                self.port_box['values']=[self.port.get()]
                self.invalidate()
                self.status.set('Wi-Fi address selected. Read device to connect. Use one active configuration client at a time.')
            return
        if self.transport.get() == 'Bluetooth':
            self.invalidate()
            self.run(bluetooth_devices(), self.bluetooth_found, 'Scanning Bluetooth for 8 seconds… BLE firmware must be enabled.')
            return
        old = self.port.get()
        ports = [f'{p} | {desc}' for p, desc in serial_ports()]
        self.port_box['values'] = ports
        if old not in ports:
            if not self.confirm_discard():return
            self.port.set(next((p for p in ports if 'USB' in p.upper()), ports[0] if ports else ''))
            self.invalidate()
        self.status.set(f'{len(ports)} serial port(s) found. Select the USB device and read it.')

    def bluetooth_found(self, devices):
        choices = [f'{address} | {name}' for address, name in devices]
        self.port_box['values'] = choices
        self.port.set(choices[0] if choices else '')
        self.status.set(f'{len(choices)} Bluetooth candidate(s). Select yours, then Read device. Windows may ask for pairing.' if choices else 'No BLE companions found. Check Bluetooth, firmware mode and existing phone connections.')
        self.edited()

    def invalidate(self):
        self.loading = True
        self.snapshot = None
        if hasattr(self, 'contact_page'): self.contact_page.clear()
        self.identity.set('Read this port to identify the device and enable supported settings.')
        for key, entry in self.entries.items():
            entry.configure(state='disabled')
            self.current[key].set('—')
            self.variables[key].set('')
        self.show_channels([])
        self.loading = False
        self.support_summary.set('NO DEVICE READ')
        self.edited()

    def edited(self):
        if self.loading or not hasattr(self, 'action_buttons'):
            return
        count, channel_count = 0, 0
        for key, entry in self.entries.items():
            changed = False
            if self.snapshot is not None and key in self.snapshot['settings']:
                try:
                    value = validate({key: parse_input(key, self.variables[key].get())})[key]
                    changed = bool(changes({key: self.snapshot['settings'][key]}, {key: value}))
                except ValueError:
                    changed = True
            count += int(changed)
            kind = 'TCombobox' if key in CHOICES else 'TEntry'
            entry.configure(style=('Changed.' if changed else '')+kind)
            self.hints[key].update_value(self.variables[key].get(), self.snapshot is not None and key in self.snapshot['settings'])
        before = {c['index']: c for c in self.snapshot.get('channels', [])} if self.snapshot else {}
        for index, (name, secret) in self.channel_vars.items():
            if index in before and (name.get() != before[index]['name'] or secret.get().lower() != before[index]['secret']):
                channel_count += 1
        self.pending.set(f'{count} setting changes  ·  {channel_count} channel slots pending' if count or channel_count else ('Up to date  ·  No pending edits' if self.snapshot else 'Read a radio to begin'))
        self.pending_count=count+channel_count
        for name, button in self.action_buttons.items():
            enabled = not self.busy and (name in ('Read device', 'Find devices', 'Batch editor') or self.snapshot is not None)
            if name == 'Review & apply':
                enabled = enabled and bool(count or channel_count)
            button.configure(state='normal' if enabled else 'disabled')
        self.location_state()
        self.filter_channels()

    def show_channels(self, channels):
        for widget in self.channel_rows.winfo_children():
            widget.destroy()
        self.channel_vars, self.channel_entries = {}, []
        self.channel_widgets = {}
        self.channel_count.set('0')
        empty = sum(not c['name'] and c['secret'] == '00'*16 for c in channels)
        maximum = self.snapshot.get('device', {}).get('max_channels', len(channels)) if self.snapshot else 0
        self.channel_count_box.configure(to=empty)
        self.channel_limit.set(f'Device maximum: {maximum} channels  ·  {len(channels)} slots read  ·  {empty} empty slots available')
        for col, label in enumerate(('Slot', 'Device channel', 'Profile channel name', 'Profile key (hidden)')):
            key = ('channel_slot', 'channel_current', 'channel_name', 'channel_secret')[col]
            help_label(self.channel_rows, label, HELP[key]).grid(row=0, column=col, sticky='w', padx=5)
        for row, channel in enumerate(channels, 1):
            index = channel['index']
            ttk.Label(self.channel_rows, text=str(index)).grid(row=row, column=0, padx=5, pady=7)
            ttk.Label(self.channel_rows, text=channel['name'] or '(empty)', width=22).grid(row=row, column=1, sticky='w')
            name, secret = tk.StringVar(value=channel['name']), tk.StringVar(value=channel['secret'])
            for col, variable in ((2, name), (3, secret)):
                entry = ttk.Entry(self.channel_rows, textvariable=variable, width=28, show='*' if col == 3 else '')
                entry.grid(row=row, column=col, padx=5, sticky='ew')
                Tooltip(entry, 'Channel name' if col == 2 else 'Channel key', HELP['channel_name' if col == 2 else 'channel_secret'])
                self.channel_entries.append(entry)
            self.channel_widgets[index] = list(self.channel_rows.grid_slaves(row=row))
            self.channel_vars[index] = (name, secret)
            name.trace_add('write', lambda *_: self.edited())
            secret.trace_add('write', lambda *_: self.edited())
        self.filter_channels()
        if not channels:
            ttk.Label(self.channel_rows, text='No successfully read channel slots. Read the device to populate this tab.').grid(row=1, column=0, columnspan=4, pady=15)

    def filter_channels(self):
        if not hasattr(self, 'channel_widgets'):
            return
        try:
            count = max(0, int(self.channel_count.get()))
        except ValueError:
            return
        before = {c['index']: c for c in self.snapshot.get('channels', [])} if self.snapshot else {}
        for index, widgets in self.channel_widgets.items():
            n, secret = self.channel_vars[index]
            old = before[index]
            occupied = bool(old['name']) or old['secret'] != '00'*16
            edited = n.get() != old['name'] or secret.get().lower() != old['secret']
            visible = occupied or edited or count > 0
            if not occupied and count > 0:
                count -= 1
            for w in widgets:
                w.grid() if visible else w.grid_remove()

    def desired_channels(self):
        return validate_channels([{'index': i, 'name': n.get(), 'secret': s.get()} for i, (n, s) in self.channel_vars.items()])

    def location_state(self):
        if self.snapshot is None or self.busy:
            return
        gps_on = parse_input('gps', self.variables['gps'].get()) == 1
        for key in ('latitude', 'longitude'):
            self.entries[key].configure(state='disabled' if gps_on or key not in self.snapshot['settings'] else 'normal')
        all_types = parse_input('manual_add_contacts', self.variables['manual_add_contacts'].get()) == 0
        for key in ('auto_add_chat', 'auto_add_repeater', 'auto_add_room_server', 'auto_add_sensor'):
            self.entries[key].configure(state='disabled' if all_types or key not in self.snapshot['settings'] else 'normal')

    def selected_port(self):
        if not self.port.get():
            raise ValueError('No serial port selected. Connect the device and refresh ports.')
        return self.port.get().split(' | ')[0]

    def run(self, operation, callback, label):
        self.busy = True
        for b in self.buttons:
            b.configure(state='disabled')
        self.port_box.configure(state='disabled')
        self.transport_box.configure(state='disabled')
        self.channel_count_box.configure(state='disabled')
        for e in self.entries.values():
            e.configure(state='disabled')
        for e in self.channel_entries:
            e.configure(state='disabled')
        self.status.set(label)
        def worker():
            try:
                self.results.put((callback, asyncio.run(operation), None))
            except Exception as exc:
                record_error('device',exc)
                self.results.put((callback, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            callback, result, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for b in self.buttons:
                b.configure(state='normal')
            self.port_box.configure(state='readonly')
            self.transport_box.configure(state='readonly')
            self.channel_count_box.configure(state='normal')
            if error:
                self.invalidate()
                self.status.set('Operation failed. Read again before applying changes.')
                messagebox.showerror('Device operation failed', error)
            else:
                try:
                    callback(result)
                except Exception as exc:
                    record_error('interface',exc)
                    self.invalidate()
                    messagebox.showerror('Could not save or display result', str(exc))
        self.poll_id = self.root.after(100, self.poll)

    def read(self):
        if not self.confirm_discard():return
        self.run(read_device(self.selected_port()), self.read_done, 'Reading settings, channels and contacts…')

    def show(self, snapshot):
        self.loading = True
        self.snapshot = snapshot
        self.editor_port_choice=self.port.get()
        self.editor_transport=self.transport.get()
        info = snapshot['device']
        self.identity.set(f"{snapshot['settings'].get('name', '?')} | {info.get('model', 'Unknown model')} | Companion | Firmware {info.get('ver', '?')} | {snapshot['port']}")
        for key, entry in self.entries.items():
            supported = key in snapshot['settings']
            value = display(key, snapshot['settings'][key]) if supported else ''
            self.variables[key].set(value)
            self.current[key].set(value if supported else 'Not reported')
            entry.configure(state='normal' if supported else 'disabled')
        self.show_channels(snapshot.get('channels', []))
        self.location_state()
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', json.dumps(snapshot, indent=2, default=str))
        self.contact_page.show(snapshot)
        self.details.configure(state='disabled')
        self.loading = False
        self.support_summary.set(f"{len(snapshot['settings'])} SETTINGS AVAILABLE   /   {len(snapshot.get('channels', []))} CHANNEL SLOTS   /   {len(snapshot.get('read_errors', {}))} READ WARNINGS")
        self.edited()

    def read_done(self, snapshot):
        previous=self.history.remember(snapshot)
        fleet_error=None
        try:self.fleet_contacts.remember(snapshot)
        except Exception as exc:
            fleet_error=str(exc);record_error('fleet contacts',exc)
        self.show(snapshot)
        path = ROOT / 'snapshots' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        save_json(path, snapshot)
        errors = snapshot.get('read_errors', {})
        self.status.set(f"Read complete; snapshot saved. {'Some optional reads failed; see reported data.' if errors else 'Ready to edit.'}")
        if previous:
            self.status.set(self.status.get() + (' Recognized radio; previous connection: '+previous['last_port']+'.'))
        if fleet_error:self.status.set(self.status.get()+' Fleet contact card was not saved: '+fleet_error)

    def desired(self):
        if self.snapshot is None:
            raise ValueError('Read the connected device first.')
        return validate({k: parse_input(k, self.variables[k].get()) for k in self.snapshot['settings']},
                        self.snapshot['self_info'].get('max_tx_power', 0))

    def load(self):
        if self.snapshot is None:
            raise ValueError('Read the device first so supported options can be checked.')
        path = filedialog.askopenfilename(filetypes=[('JSON profiles', '*.json')])
        if path:
            if not self.confirm_discard():return
            settings, channels, warnings = load_document(Path(path))
            unsupported = set(settings) - self.snapshot['settings'].keys()
            if unsupported:
                warnings.append('Unavailable settings skipped: ' + ', '.join(FIELDS[k][0] for k in sorted(unsupported)))
                settings = {k: v for k, v in settings.items() if k not in unsupported}
            unavailable_slots = [c['index'] for c in channels if c['index'] not in self.channel_vars]
            if unavailable_slots:
                raise ValueError(f'Channel slots not reported by this device: {unavailable_slots}')
            validate(settings, self.snapshot['self_info'].get('max_tx_power', 0))
            self.show(self.snapshot)
            for key, value in settings.items():
                self.variables[key].set(display(key, value))
            for c in channels:
                n, s = self.channel_vars[c['index']]
                n.set(c['name'])
                s.set(c['secret'])
            self.status.set('Profile loaded into editor. Nothing written. Review device and profile values before applying.')
            if warnings:
                messagebox.showinfo('Profile import notes', '\n\n'.join(warnings))

    def save(self):
        data = profile(self.desired(), self.desired_channels())
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON profiles', '*.json')])
        if path:
            save_json(path, data)
            self.status.set('JSON profile saved.')

    def save_snapshot(self):
        if self.snapshot is None:
            raise ValueError('Read the device first.')
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON snapshots', '*.json')])
        if path:
            save_json(path, self.snapshot)

    def apply(self):
        desired = self.desired()
        delta = changes(self.snapshot['settings'], desired)
        previous = {c['index']: c for c in self.snapshot.get('channels', [])}
        channel_delta = [c for c in self.desired_channels() if c != previous[c['index']]]
        if not delta and not channel_delta:
            self.status.set('No changes to apply.')
            return
        review = '\n'.join(f'{FIELDS[k][0]}: {display(k, self.snapshot["settings"][k])} → {display(k, v)}' for k, v in delta.items())
        for c in channel_delta:
            key_changed = c['secret'] != previous[c['index']]['secret']
            review += f"\nChannel {c['index']}: {previous[c['index']]['name'] or '(empty)'} → {c['name'] or '(empty)'}" + (' (key changes)' if key_changed else '')
        if messagebox.askokcancel('Apply these changes?', f'{self.identity.get()}\n\n{review}\n\nWrite these settings and verify by rereading?'):
            def done(result):
                self.show(result)
                self.history_page.refresh()
                self.status.set('Verified: requested values match. Apply report saved. Use Read device to refresh all channels and contacts.')
            async def recorded_apply():
                from batch import plan_device, apply_many
                plan=plan_device(self.snapshot,{'settings':delta,'channels':channel_delta})
                report,_=await apply_many([plan],ROOT/'reports',history=self.history,profile_name='Single device edit')
                item=report['devices'][0]
                if item['status']!='Verified':raise RuntimeError(item.get('error',item['status']))
                return item['after']
            self.run(recorded_apply(), done, 'Writing settings and verifying…')

    def close(self):
        if self.update_window is not None:
            if self.update_window.busy:
                messagebox.showinfo('Update in progress','Wait for the update check/download to finish before closing.',parent=self.root);return
            self.update_window.close()
        if self.batch_window is not None:
            if self.batch_window.busy:
                self.batch_window.close()
                return
            self.batch_window.close()
        if self.busy:
            messagebox.showinfo('Operation in progress', 'Wait for the device operation to finish before closing.')
        else:
            if not self.confirm_discard():return
            self.closing=True
            if self.theme_job is not None:
                self.root.after_cancel(self.theme_job);self.theme_job=None
            from preferences import save_preferences
            save_preferences(ROOT/'preferences.json',self.theme_choice.get(),self.root.geometry())
            self.root.after_cancel(self.poll_id)
            self.root.update_idletasks()
            self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
