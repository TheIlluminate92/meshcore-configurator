"""Qualitative hints, not measured runtime or an automatic configuration preset."""
import tkinter as tk
import math
from tkinter import ttk
from model import parse_input

ADVICE = {
 'rx_delay': 'Keep firmware default; advanced receive timing.',
 'airtime_factor': 'Keep firmware default; advanced airtime budget.',
 'name': 'Use a unique, recognizable name.',
 'frequency': 'Match your local mesh frequency.',
 'bandwidth': 'Match mesh. Narrower = longer airtime.',
 'spreading_factor': 'Match mesh. Higher = slower packets.',
 'coding_rate': 'Match mesh. Higher = more airtime.',
 'tx_power': 'Use lowest reliable power; range falls too.',
 'path_hash_mode': 'Keep mesh default; larger adds bytes.',
 'multi_acks': 'Start at 0; extra replies use more energy.',
 'gps': 'On for trackers; off for fixed stations.',
 'gps_interval': 'If supported: longer saves, fixes lag.',
 'latitude': 'Set for a fixed site with GPS off.',
 'longitude': 'Set for a fixed site with GPS off.',
 'advert_location_policy': 'Share if needed; small packet cost.',
 'manual_add_contacts': 'Selected types keeps discovery tidy.',
 'overwrite_oldest': 'Off keeps existing contacts when full.',
 'auto_add_chat': 'Enable to discover other companions.',
 'auto_add_repeater': 'Enable to discover repeaters.',
 'auto_add_room_server': 'Enable if you use room servers.',
 'auto_add_sensor': 'Enable if you use mesh sensors.',
 'auto_add_max_hops': 'Limit reach to reduce contact clutter.',
 'telemetry_mode_base': 'Allowed contacts if needed; replies cost.',
 'telemetry_mode_loc': 'Allow if needed; base access required.',
 'telemetry_mode_env': 'Allow if needed; base access required.',
}

ADVICE.update({
 'buzzer_quiet': 'Mute if you prefer phone alerts; modest power savings.',
 'motion_gps': 'Balanced: sleep GPS after 3 min still; movement wakes it. Experimental.',
 'led_mode': 'Unread-only reduces flashing; quiet hides normal status.',
 'screen_timeout': '15 seconds is a useful starting point; shorter saves power.',
 'screen_usb': 'Useful on a desk; normal timeout resumes on battery.',
 'usb_priority': 'Optional: prevent phone commands during USB configuration.',
})

def impact(key, value):
    """Relative impact within each setting only: None means unquantified."""
    try: v = float(parse_input(key, value))
    except (TypeError, ValueError): return None
    if not math.isfinite(v): return None
    if key == 'gps': return 5 if v else 0
    if key == 'tx_power': return 1 if v <= 0 else 2 if v <= 10 else 3 if v <= 17 else 4 if v <= 20 else 5
    if key == 'spreading_factor': return max(1, min(5, int(v)-6))
    if key == 'bandwidth': return 1 if v >= 250 else 2 if v >= 125 else 3 if v >= 62.5 else 4 if v >= 31.25 else 5
    if key == 'coding_rate': return max(1,min(5,int(v)-4))
    if key == 'multi_acks': return min(5,int(v)+1) if v else 0
    # Actual request frequency, sensors and receiver duty cycle are unknown.
    return None

class BatteryHint(ttk.Frame):
    def __init__(self, parent, key, roomy=False):
        super().__init__(parent)
        self.key = key
        self.roomy = roomy
        self.label = ttk.Label(self, text=ADVICE[key], width=1 if roomy else 31, wraplength=290 if roomy else 205, font=('Segoe UI', 9), style='Muted.TLabel')
        self.label.pack(side='left', anchor='w', fill='x' if roomy else 'none', expand=roomy)
        if roomy:
            self.bind('<Configure>', lambda event: self.label.configure(wraplength=max(100,event.width-(70 if self.canvas.winfo_manager() else 8))))
        self.canvas = tk.Canvas(self, width=57, height=20, background='white', highlightthickness=0)
        self.update_value('')

    def update_value(self, value, available=True):
        surface=ttk.Style(self).lookup('TFrame','background') or 'white'
        self.canvas.configure(background=surface)
        self.canvas.delete('all')
        level = impact(self.key, value) if available else None
        if level is None:
            self.canvas.pack_forget()
            return
        self.canvas.pack(side='left', anchor='w', before=self.label, padx=(0, 8))
        color = '#b45e36' if level >= 4 else '#007f79'
        for i in range(5):
            x = i*11+1
            self.canvas.create_rectangle(x,5,x+8,17,outline='#96a7b6',fill=color if i<level else surface)
            self.canvas.create_rectangle(x+2,3,x+6,5,outline='#96a7b6',fill='#96a7b6')
