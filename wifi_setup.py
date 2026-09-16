"""Versioned V4 network provisioning; passwords are write-only and never exported."""
import base64
from urllib.parse import urlsplit


def endpoint(value):
    value = value.strip()
    parsed = urlsplit(value if '://' in value else 'tcp://' + value)
    try:
        port = 5000 if parsed.port is None else parsed.port
    except ValueError:
        raise ValueError('Use a host or IP address and a port from 1 to 65535.') from None
    if (parsed.scheme != 'tcp' or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment or not 1 <= port <= 65535
            or any(c.isspace() for c in parsed.netloc)):
        raise ValueError('Enter a radio IP address or hostname, optionally followed by :5000.')
    return parsed.hostname, port


def encode_setup(enabled, ssid, password, port):
    ssid_bytes, password_bytes = ssid.encode('utf-8'), password.encode('utf-8')
    if '\0' in ssid or '\0' in password or len(ssid_bytes) > 32 or (enabled and not ssid_bytes):
        raise ValueError('Network name must be 1–32 UTF-8 bytes when Wi-Fi is enabled.')
    if password_bytes and not 8 <= len(password_bytes) <= 63:
        raise ValueError('Password must be 8–63 UTF-8 bytes, or empty for an open network.')
    if isinstance(port, bool) or str(port) != str(int(port)) or not 1 <= int(port) <= 65535:
        raise ValueError('TCP port must be a whole number from 1 to 65535.')
    wire = bytes([bool(enabled)]) + int(port).to_bytes(2,'little')
    wire += bytes([len(ssid_bytes), len(password_bytes)])
    wire += ssid_bytes.ljust(32,b'\0') + password_bytes.ljust(63,b'\0')
    return base64.b64encode(wire).decode('ascii')


def decode_status(custom):
    if not isinstance(custom, dict):
        raise ValueError('The radio returned invalid Wi-Fi settings.')
    if str(custom.get('wifi_schema')) != '1':
        raise ValueError('This firmware does not advertise supported Wi-Fi setup. Use the V4 triple-interface build.')
    try:
        state = int(custom['wifi_on']); port = int(custom['wifi_port'])
        ssid = bytes.fromhex(custom['wifi_ssid']).decode('utf-8')
        if state not in (0,1) or not 1 <= port <= 65535 or len(ssid.encode('utf-8')) > 32:
            raise ValueError()
    except (KeyError, ValueError, TypeError, UnicodeError):
        raise ValueError('The radio returned invalid Wi-Fi settings.') from None
    return {'enabled': bool(state), 'ssid': ssid, 'port': port, 'ip': custom.get('wifi_ip','0.0.0.0')}


async def configure(port, identity, enabled, ssid, password, tcp_port):
    if port.startswith('tcp:'):
        raise ValueError('Use USB or Bluetooth to change Wi-Fi settings, so verification survives the network restart.')
    encoded = encode_setup(enabled,ssid,password,tcp_port)
    from device import operate, event, basic
    async def apply(mc):
        before = await basic(mc,port)
        if before['self_info'].get('public_key') != identity:
            raise ValueError('A different radio is connected. Read it again before configuring Wi-Fi.')
        decode_status(before.get('custom_vars',{}))
        await event(mc.commands.set_custom_var('wifi_setup',encoded),'OK')
        after = await basic(mc,port)
        if after['self_info'].get('public_key') != identity:
            raise RuntimeError('Read-back identity mismatch after Wi-Fi setup. Read the device again.')
        status = decode_status(after.get('custom_vars',{}))
        if (status['enabled'],status['ssid'],status['port']) != (bool(enabled),ssid,int(tcp_port)):
            raise RuntimeError('Wi-Fi settings were acknowledged but read-back did not match. Read the radio again.')
        return status
    return await operate(port,apply)


def open_setup(app):
    import tkinter as tk
    from tkinter import ttk, messagebox
    if app.busy:
        return
    if not app.confirm_discard():
        return
    try:
        if not app.snapshot:
            raise ValueError('Read your V4 over USB or Bluetooth first.')
        status = decode_status(app.snapshot.get('custom_vars',{}))
        port = app.selected_port()
        if port.startswith('tcp:'):
            raise ValueError('Connect through USB or Bluetooth before changing Wi-Fi setup.')
        identity = app.snapshot['self_info']['public_key']
    except (ValueError, KeyError) as exc:
        messagebox.showerror('Wi-Fi setup',str(exc),parent=app.root); return
    window = tk.Toplevel(app.root); window.title('V4 Wi-Fi setup'); window.transient(app.root)
    window.grab_set()
    frame = ttk.Frame(window,padding=18); frame.pack(fill='both',expand=True)
    enabled=tk.BooleanVar(value=status['enabled']); ssid=tk.StringVar(value=status['ssid'])
    password=tk.StringVar(); tcp_port=tk.StringVar(value=str(status['port']))
    ttk.Checkbutton(frame,text='Enable Wi-Fi',variable=enabled).grid(row=0,columnspan=2,sticky='w')
    for row,(label,var) in enumerate((('Network name (2.4 GHz)',ssid),('Network password',password),('TCP port',tcp_port)),1):
        ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=6)
        ttk.Entry(frame,textvariable=var,width=34,show='•' if row==2 else '').grid(row=row,column=1,sticky='ew')
    ttk.Label(frame,text='Enter the password again when saving. Blank means an open network.\n'
              'Password is saved on the radio, never in app profiles or reports.\n'
              'Wi-Fi uses more power. Use a trusted LAN: Companion TCP has no login\n'
              'or encryption. Do not expose its port to the Internet.',wraplength=510).grid(row=4,columnspan=2,sticky='w',pady=12)
    ttk.Label(frame,text=f"Last reported IP: {status['ip']} • Read device again to refresh it.").grid(row=5,columnspan=2,sticky='w')
    def save():
        try:
            encode_setup(enabled.get(),ssid.get(),password.get(),tcp_port.get())
        except (ValueError,OverflowError) as exc:
            messagebox.showerror('Wi-Fi setup',str(exc),parent=window); return
        if not messagebox.askyesno('Apply Wi-Fi settings',f"Save Wi-Fi {'on' if enabled.get() else 'off'} for {ssid.get() or '(no network)'}?\nThe radio will restart its Wi-Fi connection.",parent=window):
            return
        operation=configure(port,identity,enabled.get(),ssid.get(),password.get(),tcp_port.get())
        password.set(''); window.destroy()
        def done(result):
            app.invalidate()
            app.status.set('Wi-Fi settings saved and reread. Password accepted; network connection not yet verified. Read device again for its IP.')
        app.run(operation,done,'Saving and verifying Wi-Fi setup…')
    ttk.Button(frame,text='Save & verify',command=save).grid(row=6,column=1,sticky='e',pady=(12,0))
