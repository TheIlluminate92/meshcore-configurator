"""Readable contact lists and the fleet-card picker."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from fleet_contacts import contact_rows, export_contact_list, identity

CONTACT_TYPES = {0: 'Unknown', 1: 'Companion', 2: 'Repeater', 3: 'Room', 4: 'Sensor'}


class ContactPage:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=12)
        tabs = ttk.Notebook(self.frame)
        tabs.pack(fill='both', expand=True)
        current = ttk.Frame(tabs, padding=8)
        fleet = ttk.Frame(tabs, padding=8)
        tabs.add(current, text='This radio')
        tabs.add(fleet, text='Configured radios')

        bar = ttk.Frame(current); bar.pack(fill='x', pady=(0, 8))
        self.current_summary=tk.StringVar(value='Read a radio to view its stored contacts.')
        ttk.Label(bar, textvariable=self.current_summary).pack(side='left')
        ttk.Button(bar, text='Export contact list…', command=self.export).pack(side='right')
        self.current_tree = self._tree(current, (
            ('name', 'Name', 220), ('type', 'Type', 70), ('key', 'Public key', 370),
            ('path', 'Path', 90), ('last', 'Last advert', 120)))

        fleet_bar = ttk.Frame(fleet); fleet_bar.pack(fill='x', pady=(0, 8))
        ttk.Label(fleet_bar, text='Each full read saves that radio’s signed contact card here automatically.').pack(side='left')
        ttk.Button(fleet_bar, text='Refresh', command=self.refresh_fleet).pack(side='right')
        self.fleet_tree = self._tree(fleet, (
            ('name', 'Radio', 220), ('model', 'Model', 220), ('key', 'Public key', 330), ('seen', 'Last read', 180)))
        ttk.Label(fleet, text='Use Batch editor → More → Add fleet contacts to copy selected configured radios to other radios. Contact cards can include the location advertised when the card was created.',
                  wraplength=980, style='Note.TLabel').pack(anchor='w', pady=(8, 0))
        self.snapshot = None
        self.refresh_fleet()

    @staticmethod
    def _tree(parent, columns):
        area = ttk.Frame(parent); area.pack(fill='both', expand=True)
        tree = ttk.Treeview(area, columns=[c[0] for c in columns], show='headings', selectmode='browse')
        for key, label, width in columns:
            tree.heading(key, text=label); tree.column(key, width=width, minwidth=60)
        scroll = ttk.Scrollbar(area, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); tree.pack(fill='both', expand=True)
        return tree

    def show(self, snapshot):
        self.snapshot = snapshot
        self.current_tree.delete(*self.current_tree.get_children())
        rows=contact_rows(snapshot)
        self.current_summary.set(f'{len(rows)} contacts stored on this radio.' if isinstance(snapshot.get('contacts'),dict) else 'The radio contact list was not returned; read it again before exporting.')
        for row in rows:
            key = str(row.get('public_key', ''))
            kind=row.get('type','')
            self.current_tree.insert('', 'end', values=(row.get('adv_name', ''), CONTACT_TYPES.get(kind,kind),
                key, row.get('out_path_len', ''), row.get('last_advert', '')))
        self.refresh_fleet()

    def clear(self):
        self.snapshot = None
        self.current_tree.delete(*self.current_tree.get_children())
        self.current_summary.set('Read a radio to view its stored contacts.')

    def refresh_fleet(self):
        self.fleet_tree.delete(*self.fleet_tree.get_children())
        try:
            entries = self.app.fleet_contacts.entries()
        except Exception as exc:
            messagebox.showerror('Configured radios', str(exc), parent=self.app.root)
            return
        for item in entries:
            self.fleet_tree.insert('', 'end', values=(item.get('name', '?'), item.get('model', '?'),
                item['public_key'], item.get('last_seen', '')))

    def export(self):
        if self.snapshot is None:
            messagebox.showerror('Export contact list', 'Read a radio first.', parent=self.app.root); return
        path = filedialog.asksaveasfilename(parent=self.app.root, title='Export contact list',
            defaultextension='.csv', initialfile='MeshCore-contacts.csv',
            filetypes=[('CSV spreadsheet', '*.csv'), ('JSON data', '*.json')])
        if not path: return
        count = export_contact_list(path, self.snapshot)
        self.app.status.set(f'Exported {count} contacts to {path}.')


class FleetContactPicker:
    def __init__(self, parent, entries, targets, callback):
        if not entries:
            raise ValueError('The configured-radio library is empty. Read each radio once to collect its signed contact card.')
        self.entries, self.targets, self.callback = entries, targets, callback
        self.window = tk.Toplevel(parent); self.window.title('Add fleet contacts')
        self.window.geometry('820x560'); self.window.minsize(700, 480)
        self.window.transient(parent); self.window.grab_set()
        frame = ttk.Frame(self.window, padding=16); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Add configured radios as contacts', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=f'Choose radio cards to add to {len(targets)} checked target radios. The app skips each target itself and contacts already present.',
                  wraplength=760).pack(anchor='w', pady=(6, 12))
        self.tree = ttk.Treeview(frame, columns=('name','model','key'), show='headings', selectmode='extended')
        for key,label,width in [('name','Radio',220),('model','Model',220),('key','Public key',330)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        for index,item in enumerate(entries):
            ident=str(index);self.tree.insert('','end',iid=ident,values=(item.get('name','?'),item.get('model','?'),item['public_key']))
            self.tree.selection_add(ident)
        ttk.Label(frame, text='These signed cards are public contact identities, but they may include an advertised location. Nothing is written until you approve the review.',
                  style='Note.TLabel', wraplength=760).pack(anchor='w', pady=(10, 6))
        buttons=ttk.Frame(frame);buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancel',command=self.window.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Review & add',style='Primary.TButton',command=self.review).pack(side='right')

    def review(self):
        chosen=[self.entries[int(i)] for i in self.tree.selection()]
        if not chosen:
            messagebox.showerror('Add fleet contacts','Select at least one configured radio.',parent=self.window);return
        lines=[];total=0
        for target in self.targets:
            if not isinstance(target.get('contacts'),dict):
                messagebox.showerror('Add fleet contacts',f"{target['settings'].get('name','?')} has no readable contact list. Read it again before adding contacts.",parent=self.window);return
            own=identity(target['self_info']['public_key']);existing={identity(k) for k in target['contacts']}
            additions=[e for e in chosen if identity(e['public_key']) not in existing|{own}]
            maximum=target.get('device',{}).get('max_contacts')
            if isinstance(maximum,int) and len(existing)+len(additions)>maximum:
                messagebox.showerror('Add fleet contacts',f"{target['settings'].get('name','?')} only has room for {max(0,maximum-len(existing))} more contacts; {len(additions)} would be added.",parent=self.window);return
            total+=len(additions);lines.append(f"{target['settings'].get('name','?')}: add {len(additions)}, skip {len(chosen)-len(additions)}")
        if total==0:
            messagebox.showinfo('Add fleet contacts','Every chosen radio is already present or is the target itself.',parent=self.window);return
        if not messagebox.askokcancel('Add reviewed contacts?', '\n'.join(lines)+f'\n\n{total} total verified contact additions will be attempted.', parent=self.window):return
        self.window.destroy();self.callback(chosen)
