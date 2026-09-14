# T1000-E options — configurator 0.7.2-dev

Use Device options to configure compatible firmware's buzzer (enabled/muted),
status LED on battery (normal/unread-only/quiet), and USB configuration priority.
Controls are enabled only if firmware explicitly advertises support. Existing
T114 screen controls remain available on compatible T114 firmware.

Settings can be saved in JSON profiles and applied in the batch editor. Missing
capabilities block writes; successful writes must verify by rereading. Physical
radio behavior remains untested on this candidate. Start with one device.

125 local tests passed. The packaged app starts with 28 settings and history.
The -dev version's update-check handling is fixed; stable remote versions still
require valid release metadata and a verified executable.

Motion-aware GPS is not implemented or included. Existing GPS behavior remains.
No new melodies, volume control, button shortcuts, find-radio or battery alerts.
This development build is not distributed through the stable app updater yet.
