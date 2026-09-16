"""Modal fleet workspace; only one device operation can run at a time."""
import asyncio
import copy
import queue
import threading
from diagnostics import record_error
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime
from device import serial_ports, bluetooth_devices, read_device, save_json, add_contacts
from model import FIELDS, display
from batch import plan_many, apply_many

class BatchWindow:
    def __init__(self, app, document=None):
        self.app=app;self.document=copy.deepcopy(document or {'name':'Batch editor','settings':{},'channels':[]})
        self.shared_initialized=document is not None
        for key in ('name','latitude','longitude'):self.document['settings'].pop(key,None)
        self.individual={}
        self.window=tk.Toplevel(app.root);self.window.title('Batch editor — '+self.document['name'])
        self.window.geometry('1050x720');self.window.minsize(900,650)
        self.window.transient(app.root);self.window.grab_set()
        self.busy=False;self.cancel=threading.Event();self.queue=queue.Queue()
        app.batch_window=self
        self.targets={};self.snapshots={};self.plans=None;self.controls=[]
        self.next_target_id=0;self.checked_state=()
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        f=ttk.Frame(self.window,padding=16);f.pack(fill='both',expand=True)
        footer=ttk.Frame(f);footer.pack(side='bottom',fill='x')
        header=ttk.Frame(f);header.pack(fill='x',pady=(0,10))
        ttk.Label(header,text='Batch editor',font=('Segoe UI',16,'bold')).pack(side='left')
        self.discovery=tk.StringVar(value='USB')
        self.discovery_box=ttk.Combobox(header,textvariable=self.discovery,values=['USB','Bluetooth'],state='readonly',width=11)
        self.discovery_box.pack(side='right',padx=6)
        self.controls.append(self.discovery_box)
        def button(parent,title,action):
            b=ttk.Button(parent,text=title,command=lambda:self.guard(action));b.pack(side='left',padx=(0,6));self.controls.append(b);return b
        discovery_actions=ttk.Frame(header);discovery_actions.pack(side='right')
        button(discovery_actions,'Find',lambda:self.find_ble() if self.discovery.get()=='Bluetooth' else self.find_usb())
        button(discovery_actions,'Read',self.read_selected)
        self.heading=tk.StringVar(value='Shared settings: '+self.document['name'])
        profilebar=ttk.Frame(f);profilebar.pack(fill='x',pady=(0,8))
        ttk.Label(profilebar,text='Profile for checked radios').pack(side='left',padx=(0,8))
        self.profile_choices=self.app.profile_page.library.entries()[0]
        self.profile_choice=tk.StringVar(value=self.document['name'])
        self.profile_box=ttk.Combobox(profilebar,textvariable=self.profile_choice,values=[e['name'] for e in self.profile_choices],state='readonly',width=28)
        self.profile_box.pack(side='left',padx=(0,8));self.controls.append(self.profile_box)
        self.profile_box.bind('<<ComboboxSelected>>',lambda _:self.guard(self.use_profile))
        button(profilebar,'Edit shared',self.edit_shared)
        button(profilebar,'Compare',self.compare)
        more=ttk.Menubutton(profilebar,text='More');more.pack(side='left');self.controls.append(more)
        menu=tk.Menu(more,tearoff=False);more.configure(menu=menu)
        menu.add_command(label='Export dry run…',command=lambda:self.guard(self.export_dry_run))
        menu.add_command(label='Compatibility review…',command=lambda:self.guard(self.compatibility))
        menu.add_command(label='Individual names & positions…',command=lambda:self.guard(self.individual_step))
        menu.add_command(label='Save shared profile…',command=lambda:self.guard(self.save_shared))
        menu.add_separator()
        menu.add_command(label='Add fleet contacts…',command=lambda:self.guard(self.add_fleet_contacts))
        self.all_checked=tk.BooleanVar(value=False)
        self.master_check=ttk.Checkbutton(f,text='All devices',variable=self.all_checked,command=self.toggle_all)
        self.master_check.pack(anchor='w');self.controls.append(self.master_check)
        device_area=ttk.Frame(f);device_area.pack(fill='both',expand=True,pady=(4,6))
        self.tree=ttk.Treeview(device_area,columns=('port','name','status'),show='tree headings',selectmode='none',height=7)
        self.tree.column('#0',width=34,minwidth=34,stretch=False)
        for key,label,width in [('port','Connection',150),('name','Device',230),('status','Status',430)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width)
        device_scroll=ttk.Scrollbar(device_area,orient='vertical',command=self.tree.yview)
        device_scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=device_scroll.set)
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Button-1>',self.toggle_row)
        self.tree.bind('<space>',self.toggle_focused)
        self.tree.bind('<<TreeviewSelect>>',lambda _:self.selection_changed())
        self.device_summary=tk.StringVar(value='Check devices, then Read. Each checked connection is tried; unreadable devices are skipped during reading.')
        ttk.Label(f,textvariable=self.device_summary,wraplength=840).pack(anchor='w',pady=(0,6))
        details=ttk.LabelFrame(f,text='Review changes / results',padding=6);details.pack(fill='both',expand=True,pady=(0,8))
        self.details=tk.Text(details,height=5,wrap='word',font=('Consolas',10),state='disabled')
        scroll=ttk.Scrollbar(details,command=self.details.yview);self.details.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.details.pack(fill='both',expand=True)
        self.set_details('Choose a profile or edit shared settings, then Review. Proposed changes appear here before anything is written.')
        actions=ttk.Frame(footer);actions.pack(fill='x',pady=(0,6))
        button(actions,'Review',self.review)
        self.apply_button=button(actions,'Apply',self.apply);self.apply_button.configure(state='disabled')
        self.status=tk.StringVar(value='Find and select the devices you want to configure.')
        ttk.Label(footer,textvariable=self.status,wraplength=850).pack(anchor='w')
        self.progress_value=tk.DoubleVar(value=0)
        self.progress_label=tk.StringVar(value='')
        ttk.Label(footer,textvariable=self.progress_label).pack(anchor='w',pady=(6,2))
        self.progress_bar=ttk.Progressbar(footer,variable=self.progress_value,maximum=1);self.progress_bar.pack(fill='x')
        self.progress_statuses={};self.progress_ports=[]
        self.stop=ttk.Button(footer,text='Stop after current device',command=self.cancel.set,state='disabled');self.stop.pack(anchor='e',pady=(8,0))
        self.poll_id=self.window.after(100,self.poll)
        self.find_usb()

    def use_profile(self):
        self.refresh_profiles()
        chosen=next((e for e in self.profile_choices if e['name']==self.profile_choice.get()),None)
        if chosen is None:raise ValueError('That saved profile is no longer available. Choose another profile.')
        self.document=copy.deepcopy(chosen)
        for key in ('name','latitude','longitude'):self.document['settings'].pop(key,None)
        self.shared_initialized=True;self.individual={};self.invalidate_review()
        self.heading.set('Shared settings: '+self.document['name'])
        from comparison import profile_text
        self.set_details(profile_text(self.document))
        self.status.set('Profile loaded for checked radios. Individual names and positions stay separate. Review before applying.')

    def refresh_profiles(self):
        self.profile_choices=self.app.profile_page.library.entries()[0]
        self.profile_box.configure(values=[e['name'] for e in self.profile_choices])

    def shared_edited(self):
        self.profile_choice.set(self.document['name']+' (edited)')
        self.heading.set('Shared settings: '+self.document['name']+' (edited)')

    def toggle_all(self):
        if self.busy:return
        self.tree.selection_set(self.tree.get_children() if self.all_checked.get() else ())
        self.selection_changed()

    def toggle_row(self,event):
        if self.tree.identify_region(event.x,event.y) not in ('tree','cell'):return
        row=self.tree.identify_row(event.y)
        if not row or self.busy:return 'break'
        self.tree.focus_set();self.tree.focus(row)
        self.toggle_focused()
        return 'break'

    def toggle_focused(self,event=None):
        row=self.tree.focus()
        if row and not self.busy:
            if row in self.tree.selection():self.tree.selection_remove(row)
            else:self.tree.selection_add(row)
            self.selection_changed()
        return 'break'

    def selection_changed(self):
        checked=tuple(self.tree.selection())
        if checked!=self.checked_state:
            self.invalidate_review();self.checked_state=checked
        selected=set(self.tree.selection());children=self.tree.get_children()
        self.all_checked.set(bool(children) and len(selected)==len(children))
        self.master_check.state(['alternate'] if selected and len(selected)!=len(children) else ['!alternate'])
        for row in children:self.tree.item(row,text='☑' if row in selected else '☐')
        row=self.tree.focus()
        if row:
            port,name,status=self.tree.item(row,'values')
            snapshot=self.snapshots.get(port)
            brief=f'{name} · {port} · {status}'
            if snapshot:brief+=f" · {len(snapshot['settings'])} settings · {len(snapshot.get('channels',[]))} channels"
            self.device_summary.set(brief)

    def guard(self,action):
        if self.busy:return
        try:action()
        except Exception as exc:record_error('batch',exc);messagebox.showerror('Multiple devices',str(exc),parent=self.window)

    def invalidate_review(self):
        self.plans=None
        self.apply_button.configure(state='disabled')

    def add_targets(self,targets):
        self.invalidate_review()
        for port,name in targets:
            if port in self.targets:continue
            ident=str(self.next_target_id);self.next_target_id+=1;self.targets[port]=ident
            self.tree.insert('','end',iid=ident,text='☐',values=(port,name,'Not read'))
            self.tree.selection_add(ident)
        self.selection_changed()

    def find_usb(self):
        found=serial_ports();present={p for p,_ in found}
        for port in list(self.targets):
            if not port.startswith('ble:') and port not in present:
                self.tree.delete(self.targets.pop(port));self.snapshots.pop(port,None)
        self.add_targets(found)
    def find_ble(self):self.run(bluetooth_devices(),self.add_targets,'Scanning Bluetooth…')
    def select_all(self):self.tree.selection_set(self.tree.get_children())
    def selected(self):
        ports=[self.tree.item(i,'values')[0] for i in self.tree.selection()]
        if not ports:raise ValueError('Select at least one device.')
        return ports

    def update(self,port,status,name=None):
        i=self.targets[port];values=list(self.tree.item(i,'values'));values[2]=status
        if name is not None:values[1]=name
        self.tree.item(i,values=values)
        if port in self.progress_ports:
            self.progress_statuses[port]=status
            terminal={'Verified','No changes at review','Failed — reread required','Not attempted','Read complete','Not read — stopped'}
            finished=sum(s in terminal or s.startswith(('Read failed:','Read complete')) for s in self.progress_statuses.values())
            verified=sum(s=='Verified' for s in self.progress_statuses.values())
            failed=sum(s.startswith('Failed') or s.startswith('Read failed:') for s in self.progress_statuses.values())
            self.progress_value.set(finished)
            self.progress_label.set(f'{finished} / {len(self.progress_ports)} finished · {verified} verified · {failed} failed')

    def run(self,operation,callback,status):
        self.busy=True;self.cancel.clear();self.status.set(status)
        for b in self.controls:b.configure(state='disabled')
        self.stop.configure(state='normal')
        def worker():
            try:self.queue.put(('done',callback,asyncio.run(operation),None))
            except Exception as exc:record_error('batch',exc);self.queue.put(('done',callback,None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def read_selected(self):
        ports=self.selected();self.invalidate_review()
        self.individual={}
        self.start_progress(ports)
        for p in ports:self.snapshots.pop(p,None)
        async def read():
            results={}
            for port in ports:
                if self.cancel.is_set():self.queue.put(('progress',port,'Not read — stopped'));continue
                self.queue.put(('progress',port,'Reading…'))
                try:
                    snapshot=await read_device(port)
                    save_json(self.app.profile_page.library.folder.parent/'snapshots'/('fleet-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'),snapshot)
                    previous=self.app.history.remember(snapshot)
                    try:self.app.fleet_contacts.remember(snapshot)
                    except Exception as exc:
                        snapshot.setdefault('read_errors',{})['fleet_contact_library']=str(exc)
                        record_error('fleet contacts',exc)
                    snapshot['recognized_from']=previous['last_port'] if previous else None
                    results[port]=snapshot
                    self.queue.put(('progress',port,'Read complete'))
                except Exception as exc:record_error('batch',exc);self.queue.put(('progress',port,'Read failed: '+str(exc)))
            return results
        def done(results):
            self.snapshots.update(results)
            for p,s in results.items():self.update(p,'Read complete'+(' · recognized from '+s['recognized_from'] if s.get('recognized_from') else ''),s['settings'].get('name','?'))
            self.status.set(f'{len(results)} of {len(ports)} devices read. Uncheck failed devices before review.')
            self.device_summary.set(f'{len(results)} readable radios · {len(ports)-len(results)} unreadable connections')
        self.run(read(),done,'Reading selected devices…')

    def add_fleet_contacts(self):
        snapshots=self.selected_snapshots()
        from contact_ui import FleetContactPicker
        FleetContactPicker(self.window,self.app.fleet_contacts.entries(),snapshots,self.apply_fleet_contacts)

    def apply_fleet_contacts(self,entries):
        ports=self.selected();snapshots={p:self.snapshots[p] for p in ports}
        self.start_progress(ports)
        async def work():
            results={}
            for port in ports:
                if self.cancel.is_set():
                    self.queue.put(('progress',port,'Not attempted'));continue
                self.queue.put(('progress',port,'Adding contacts…'))
                try:
                    result=await add_contacts(port,snapshots[port],entries,self.app.profile_page.library.folder.parent/'reports')
                    results[port]=result
                    self.queue.put(('progress',port,'Verified'))
                except Exception as exc:
                    record_error('batch contacts',exc)
                    self.queue.put(('progress',port,'Failed — reread required'))
                    raise
            return results
        def done(results):
            lines=[]
            for port,result in results.items():
                self.snapshots[port]['contacts']=result['contacts']
                lines.append(f"{self.snapshots[port]['settings'].get('name','?')} — added {result['added']}, skipped {result['skipped']}\n  {result['report_path']}")
            self.set_details('\n'.join(lines));self.status.set(f'Fleet contacts verified on {len(results)} devices.')
        self.run(work(),done,'Adding and verifying fleet contacts…')

    def start_progress(self,ports):
        self.progress_ports=list(ports);self.progress_statuses={}
        self.progress_bar.configure(maximum=max(1,len(ports)));self.progress_value.set(0)
        self.progress_label.set(f'0 / {len(ports)} finished')

    def compare(self):
        from compare_ui import compare
        compare(self.window,self.selected_snapshots(),self.document)

    def selected_snapshots(self):
        ports=self.selected()
        missing=[p for p in ports if p not in self.snapshots]
        if missing:raise ValueError('Read these devices first: '+', '.join(missing))
        snapshots=[self.snapshots[p] for p in ports]
        plan_many(snapshots,{'settings':{},'channels':[]})
        return snapshots

    def edit_shared(self):
        from compatibility import check_role
        check_role(self.document)
        from batch_editor import SharedEditor
        self.invalidate_review()
        SharedEditor(self,self.selected_snapshots())

    def individual_step(self):
        from batch_editor import IndividualWizard
        self.invalidate_review()
        IndividualWizard(self,self.selected_snapshots())

    def save_shared(self):
        from compatibility import check_role
        check_role(self.document)
        name=simpledialog.askstring('Save shared profile','Name for these shared settings:',parent=self.window)
        if name is None:return
        library=self.app.profile_page.library
        ident=library.save(name,self.document['settings'],self.document.get('channels',[]),naming=self.document.get('naming'))
        self.app.profile_page.refresh(ident)
        self.refresh_profiles()
        self.document['name']=name.strip();self.profile_choice.set(name.strip())
        self.heading.set('Shared settings: '+name.strip())
        self.status.set('Shared profile saved. Individual names and positions are kept out of it.')

    def set_details(self,text):
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('1.0',text);self.details.configure(state='disabled')

    def export_dry_run(self):
        ports=self.selected()
        path=filedialog.asksaveasfilename(parent=self.window,title='Save dry run (may contain names and locations)',defaultextension='.json',initialfile='MeshCore-batch-dry-run.json',filetypes=[('Dry run JSON','*.json')])
        if not path:return
        from dry_run import export
        export(path,[self.snapshots[p] for p in ports if p in self.snapshots],self.document,self.individual,[p for p in ports if p not in self.snapshots])
        self.status.set('Dry run saved. Includes compatibility and any reviewed individual names; no settings written, channel keys excluded.')

    def compatibility(self):
        from compatibility import show
        show(self.window,self.selected_snapshots(),self.document)

    def review(self):
        self.invalidate_review();ports=self.selected()
        missing=[p for p in ports if p not in self.snapshots]
        if missing:raise ValueError('Read these devices first: '+', '.join(missing))
        from compatibility import text as compatibility_text, review as compatibility_review
        summary=compatibility_text([self.snapshots[p] for p in ports],self.document)
        self.set_details(summary)
        if any(compatibility_review(self.snapshots[p],self.document)[1] for p in ports):
            self.status.set('Compatibility blocked. Edit the profile or uncheck incompatible radios, then review again.');return
        if any(self.snapshots[p]['self_info']['public_key'] not in self.individual for p in ports):
            self.individual_step();return
        errors=[]
        from batch import plan_device
        for p in ports:
            target=copy.deepcopy(self.document)
            target['settings'].update(self.individual[self.snapshots[p]['self_info']['public_key']])
            try:plan_device(self.snapshots[p],target);self.update(p,'Compatible')
            except Exception as exc:errors.append(p+': '+str(exc));self.update(p,'Blocked: '+str(exc))
        if errors:self.set_details('\n'.join(errors));return
        plans=plan_many([self.snapshots[p] for p in ports],self.document,self.individual)
        lines=[summary,'Proposed values','']
        for plan in plans:
            s=plan['baseline'];lines.append(f"{s['settings'].get('name','?')} — {plan['port']}")
            for k,v in plan['settings'].items():lines.append(f"  {FIELDS[k][0]}: {display(k,s['settings'][k])} → {display(k,v)}")
            before={c['index']:c for c in s.get('channels',[])}
            for c in plan['channels']:
                old=before[c['index']]
                lines.append(f"  Channel {c['index']}: {old['name'] or '(empty)'} → {c['name'] or '(empty)'}"+(' [key changes]' if c['secret']!=old['secret'] else ''))
            if not plan['settings'] and not plan['channels']:lines.append('  No changes')
            lines.append('')
        self.plans=plans;self.set_details('\n'.join(lines));self.apply_button.configure(state='normal' if any(p['settings'] or p['channels'] for p in plans) else 'disabled')
        self.status.set('Review shared changes and individual names/positions above. Nothing has been written yet.')

    def apply(self):
        if not self.plans:raise ValueError('Review the selected devices first.')
        plans=copy.deepcopy(self.plans)
        if not messagebox.askokcancel('Apply reviewed batch?',f"Apply {self.document['name']} to {len(plans)} reviewed devices?\nEach changed device will be reread and verified. A failure stops the batch; completed devices are not rolled back.",parent=self.window):return
        self.invalidate_review()
        self.start_progress([p['port'] for p in plans])
        async def work():
            return await apply_many(plans,self.app.profile_page.library.folder.parent/'reports',self.cancel.is_set,lambda p,s:self.queue.put(('progress',p,s)),history=self.app.history,profile_name=self.document['name'])
        def done(result):
            report,path=result
            for p in plans:self.snapshots.pop(p['port'],None)
            self.set_details('\n'.join(f"{d['name']} — {d['port']}: {d['status']}"+ ('\n'+d['error'] if 'error' in d else '') for d in report['devices']))
            self.status.set(f'Batch finished. Report: {path}. Read again before another batch.')
            self.app.invalidate()
            self.app.history_page.refresh()
        self.run(work(),done,'Applying reviewed changes…')

    def poll(self):
        try:
            while True:
                message=self.queue.get_nowait()
                if message[0]=='progress':self.update(message[1],message[2]);continue
                _,callback,result,error=message;self.busy=False
                for b in self.controls:b.configure(state='readonly' if isinstance(b,ttk.Combobox) else 'normal')
                self.stop.configure(state='disabled');self.invalidate_review()
                if error:
                    self.snapshots.clear();self.app.invalidate();self.status.set(error)
                    messagebox.showerror('Batch operation failed',error,parent=self.window)
                else:
                    try:callback(result)
                    except Exception as exc:record_error('batch',exc);self.status.set(str(exc));messagebox.showerror('Batch result',str(exc),parent=self.window)
        except queue.Empty:pass
        self.poll_id=self.window.after(100,self.poll)

    def close(self):
        if self.busy:
            self.cancel.set();self.status.set('Stopping after the current device. Wait for its operation to finish.');return
        self.window.after_cancel(self.poll_id);self.window.destroy();self.app.batch_window=None
