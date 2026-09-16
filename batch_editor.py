"""Shared-settings editor and per-radio naming walkthrough. No I/O to radios."""
import copy
import tkinter as tk
from tkinter import ttk, messagebox
from setting_box import SettingBox
from model import FIELDS, CHOICES, validate, display, parse_input, validate_naming
from batch import plan_device, plan_many

class SharedEditor:
    def __init__(self, owner, snapshots):
        self.owner=owner;self.snapshots=snapshots
        self.window=tk.Toplevel(owner.window);self.window.title('1. Shared settings');self.window.transient(owner.window);self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        f=ttk.Frame(self.window,padding=16);f.pack(fill='both',expand=True)
        ttk.Label(f,text=f'Same settings for {len(snapshots)} devices',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(f,text='Checked fields are applied to every selected radio. Names and optional fixed positions come next.\nValues start from the saved profile, or the first selected radio. Unchecked fields stay unchanged.').pack(anchor='w',pady=8)
        tabs=ttk.Notebook(f);tabs.pack(fill='both',expand=True)
        groups=[('Advanced', ('rx_delay','airtime_factor')),
                ('Device options', ('buzzer_quiet','led_mode','screen_timeout','screen_usb','usb_priority')),
                ('Radio',('frequency','bandwidth','spreading_factor','coding_rate','tx_power','path_hash_mode','multi_acks')),
                ('GPS & telemetry',('gps','motion_gps','gps_interval','advert_location_policy','telemetry_mode_base','telemetry_mode_loc','telemetry_mode_env')),
                ('Discovery',('manual_add_contacts','overwrite_oldest','auto_add_chat','auto_add_repeater','auto_add_room_server','auto_add_sensor','auto_add_max_hops'))]
        common=set.intersection(*(set(s['settings']) for s in snapshots))
        source=owner.document['settings']
        self.values={};self.include={}
        for title,keys in groups:
            page=ttk.Frame(tabs,padding=12);tabs.add(page,text=title)
            for row,key in enumerate(keys):
                enabled=key in common
                check=tk.BooleanVar(value=enabled and (key in source if source or owner.shared_initialized else True))
                value=tk.StringVar(value=display(key,source.get(key,snapshots[0]['settings'].get(key,''))))
                self.include[key]=check;self.values[key]=value
                ttk.Checkbutton(page,text=FIELDS[key][0],variable=check,state='normal' if enabled else 'disabled').grid(row=row,column=0,sticky='w',padx=(0,16),pady=6)
                if key in CHOICES:
                    entry=SettingBox(page,textvariable=value,values=list(CHOICES[key].values()),width=36,state='normal' if enabled else 'disabled')
                else:entry=ttk.Entry(page,textvariable=value,width=36,state='normal' if enabled else 'disabled')
                entry.grid(row=row,column=1,sticky='ew',pady=6)
                if not enabled:ttk.Label(page,text='Not reported by every device',style='Muted.TLabel').grid(row=row,column=2,padx=8)
        self.channels=copy.deepcopy(owner.document.get('channels',[]))
        self.channel_mode=tk.StringVar(value='Profile channels' if self.channels else 'Leave channels unchanged')
        ttk.Label(f,text='Shared channels').pack(anchor='w',pady=(12,4))
        modes=['Leave channels unchanged','Copy all slots from first device']
        if self.channels:modes.append('Profile channels')
        ttk.Combobox(f,textvariable=self.channel_mode,values=modes,state='readonly',width=44).pack(anchor='w')
        ttk.Label(f,text='Copying all slots includes empty slots and can clear channels on other radios. The final review lists every changed slot.',wraplength=780,style='Muted.TLabel').pack(anchor='w',pady=6)
        ttk.Button(f,text='Next: individual devices →',style='Primary.TButton',command=self.save).pack(anchor='e',pady=(8,0))

    def close(self):self.window.destroy();self.owner.window.grab_set()

    def save(self):
        try:
            values=validate({k:parse_input(k,self.values[k].get()) for k,check in self.include.items() if check.get()})
            mode=self.channel_mode.get()
            channels=self.channels if mode=='Profile channels' else copy.deepcopy(self.snapshots[0].get('channels',[])) if mode=='Copy all slots from first device' else []
            document={'name':self.owner.document.get('name','Batch editor'),'settings':values,'channels':channels,'naming':validate_naming(self.owner.document.get('naming'))}
            for s in self.snapshots:plan_device(s,document)
        except Exception as exc:messagebox.showerror('Shared settings',str(exc),parent=self.window);return
        self.owner.document=document;self.owner.individual={};self.owner.invalidate_review()
        self.owner.shared_initialized=True
        self.owner.heading.set('Shared settings: Batch editor')
        if hasattr(self.owner,'shared_edited'):self.owner.shared_edited()
        self.close();self.owner.individual_step()

class IndividualWizard:
    def __init__(self,owner,snapshots):
        self.owner=owner;self.snapshots=copy.deepcopy(snapshots);self.index=0
        self.draft=copy.deepcopy(owner.individual)
        self.window=tk.Toplevel(owner.window);self.window.title('2. Individual devices');self.window.transient(owner.window);self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        f=ttk.Frame(self.window,padding=20);f.pack(fill='both',expand=True)
        self.heading=tk.StringVar();self.identity=tk.StringVar();self.name=tk.StringVar()
        self.fixed=tk.BooleanVar();self.lat=tk.StringVar();self.lon=tk.StringVar()
        ttk.Label(f,textvariable=self.heading,font=('Segoe UI',16,'bold')).grid(row=0,column=0,columnspan=2,sticky='w')
        ttk.Label(f,textvariable=self.identity,wraplength=640,style='Muted.TLabel').grid(row=1,column=0,columnspan=2,sticky='w',pady=12)
        ttk.Label(f,text='Unique device name').grid(row=2,column=0,sticky='w')
        self.entry=ttk.Entry(f,textvariable=self.name,width=38);self.entry.grid(row=2,column=1,padx=(16,0),pady=8)
        prefix=ttk.Frame(f);prefix.grid(row=3,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Label(prefix,text='Or number the whole batch:').pack(side='left')
        template=validate_naming(owner.document.get('naming'))
        self.used_naming=copy.deepcopy(template)
        self.prefix=tk.StringVar(value=template['prefix']);self.start=tk.StringVar(value=str(template['start']))
        ttk.Entry(prefix,textvariable=self.prefix,width=16).pack(side='left',padx=8)
        ttk.Label(prefix,text='Start:').pack(side='left')
        ttk.Spinbox(prefix,from_=1,to=999999,textvariable=self.start,width=6).pack(side='left',padx=6)
        ttk.Button(prefix,text='Number all: -01, -02…',command=self.number).pack(side='left')
        self.fixed_button=ttk.Checkbutton(f,text='Set a fixed position for this device (GPS must be off)',variable=self.fixed,command=self.position_state)
        self.fixed_button.grid(row=4,column=0,columnspan=2,sticky='w',pady=8)
        self.coords=[]
        for row,label,var in [(5,'Latitude',self.lat),(6,'Longitude',self.lon)]:
            ttk.Label(f,text=label).grid(row=row,column=0,sticky='w')
            e=ttk.Entry(f,textvariable=var,width=38);e.grid(row=row,column=1,padx=(16,0),pady=6);self.coords.append(e)
        ttk.Label(f,text='Device keys and identities are preserved. Names must differ within this batch.\nNext only stages edits; nothing is written until the final review is approved.',wraplength=640,style='Muted.TLabel').grid(row=7,column=0,columnspan=2,sticky='w',pady=12)
        buttons=ttk.Frame(f);buttons.grid(row=8,column=0,columnspan=2,sticky='e')
        ttk.Button(buttons,text='Cancel',command=self.close).pack(side='left',padx=6)
        self.back=ttk.Button(buttons,text='← Previous',command=lambda:self.move(-1));self.back.pack(side='left',padx=6)
        self.next=ttk.Button(buttons,text='Next →',style='Primary.TButton',command=lambda:self.move(1));self.next.pack(side='left',padx=6)
        self.show()

    def current(self):return self.snapshots[self.index]

    def show(self):
        s=self.current();values=self.draft.get(s['self_info']['public_key'],{})
        self.heading.set(f'Device {self.index+1} of {len(self.snapshots)}')
        key=str(s['self_info']['public_key'])[:12]
        self.identity.set(f"{s['port']}  ·  {s['device'].get('model','Radio')}  ·  ID {key}\nCurrent name: {s['settings'].get('name','?')}")
        self.name.set(values.get('name',s['settings'].get('name','')))
        self.fixed.set('latitude' in values or 'longitude' in values)
        self.lat.set(str(values.get('latitude',s['settings'].get('latitude',0))))
        self.lon.set(str(values.get('longitude',s['settings'].get('longitude',0))))
        self.position_state()
        self.back.configure(state='normal' if self.index else 'disabled')
        self.next.configure(text='Finish & review' if self.index==len(self.snapshots)-1 else 'Next →')
        self.entry.focus_set();self.entry.selection_range(0,'end')

    def position_state(self):
        s=self.current();gps=self.owner.document['settings'].get('gps',s['settings'].get('gps',0))
        allowed=gps!=1 and {'latitude','longitude'}<=s['settings'].keys()
        if not allowed:self.fixed.set(False)
        self.fixed_button.configure(state='normal' if allowed else 'disabled')
        for e in self.coords:e.configure(state='normal' if allowed and self.fixed.get() else 'disabled')

    def capture(self):
        values={'name':self.name.get()}
        if self.fixed.get():values.update(latitude=self.lat.get(),longitude=self.lon.get())
        values=validate(values)
        self.draft[self.current()['self_info']['public_key']]=values

    def number(self):
        try:
            template=validate_naming({'prefix':self.prefix.get(),'start':int(self.start.get())})
            names=[validate({'name':f"{template['prefix']}-{i+template['start']:02d}"})['name'] for i in range(len(self.snapshots))]
            self.name.set(names[self.index]);self.capture()
            self.used_naming=template
            for s,name in zip(self.snapshots,names):self.draft.setdefault(s['self_info']['public_key'],{})['name']=name
            self.show()
        except Exception as exc:messagebox.showerror('Names',str(exc),parent=self.window)

    def move(self,direction):
        try:
            self.capture()
            if direction==1 and self.index==len(self.snapshots)-1:
                plan_many(self.snapshots,self.owner.document,self.draft)
                self.owner.document['naming']=copy.deepcopy(self.used_naming)
                self.owner.individual=copy.deepcopy(self.draft);self.close();self.owner.review();return
            self.index+=direction;self.show()
        except Exception as exc:messagebox.showerror('Individual values',str(exc),parent=self.window)

    def close(self):self.window.destroy();self.owner.window.grab_set()
