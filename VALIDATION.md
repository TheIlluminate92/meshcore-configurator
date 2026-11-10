# Validation status

Current source and published stable release are **0.7.7** (reviewed November 9,
2026); see the [README](README.md) and [release history](CHANGELOG.md). The
0.7.0 / 116-test record below is historical. The current README reports 147 tests;
retain its original evidence and obtain the exact newer run receipt before
treating that total as independently verified by this documentation review.
Hardware acceptance limits below remain in force unless newer dated evidence
explicitly supersedes them.

## Historical 0.7.0 validation record

Historical application version: **0.7.0**. Its recorded local run: **116 automated tests passed**, plus portable executable startup with 23 controls and history initialization. Documentation maintenance does not constitute a new application test run.

| Area | Evidence / remaining work |
| --- | --- |
| Settings and profile validation | Automated coverage for supported values, groups, scope preservation and malformed input |
| Batch selection and profiles | Automated coverage for checkbox state, review invalidation, removed USB rows, profile refresh and individual overrides |
| Failure and cancellation | Simulated read continuation, write-stop behavior, saved per-device results and interrupted-run handling |
| UI | Populated settings pages checked at minimum/full-screen sizes; batch footer fit; theme switching and battery ordering tested |
| Portable application | Built EXE starts with bundled dependencies; existing desktop data copied to the local handoff folder, originals retained |
| USB reading | Prior T114 v1.17.1 read: 22 settings, 40 channel slots, no optional read errors |
| Hardware writes | Expanded real-device writes and multi-radio batches still need bench testing |
| Bluetooth | Code and simulated transport tests exist; live connection/read/write unvalidated |
| Restart persistence | Identity matching and expected-value comparison tested with synthetic reads; real power-cycle persistence unvalidated |
| T1000-E | Magnetic USB and board-specific behavior unvalidated |
| Updates | Version/digest/path/redirect safeguards and tampered/independent staging tested. Disposable Windows helper test passes: parent exit wait, EXE replacement, restart, retained backup and user data. Anonymous v0.5.1 release lookup and EXE download passed with SHA-256 verification against public GitHub. Packaged self-update probe passes and gates releases. User confirmed the 0.5.3 → 0.5.4 update/restart |
| Release pipeline | 0.7.0 Windows EXE and portable ZIP are published. Release checks include the unit suite and packaged restart probe |

## Next bench checks

Use the T114 bench unit first: make one deliberate setting change, review it, apply, verify, restart manually, and check the saved expectations. Then test a two-radio batch with unique names and a deliberate unavailable connection. Validate BLE and T1000-E separately. Keep resulting snapshots and reports local.

An update test needs a newer published release; public access requires no token. Confirm that the version changes after restart and profiles/history remain intact. Retain the previous executable until this succeeds.

The explicit `integration_update_probe.py` check compiles harmless Windows executables in a temporary folder and runs the real replacement helper. It never opens radios or reads the user workspace. Fault-injection unit tests additionally cover interrupted/concurrent saves, preference write failures, newer database schemas, post-write identity/channel mismatches and disconnect errors.

## 0.5.3 restart regression

All 94 unit tests pass. The real one-file `integration_frozen_restart.py` probe replaces and restarts itself using the production helper, then confirms a fresh, existing PyInstaller extraction directory. The earlier non-PyInstaller helper test did not cover inherited runtime state. The frozen probe now also gates release publishing. Downloads-to-update-to-GUI on the user installation still needs confirmation; existing profiles and radios were not modified.

## 0.6.0 recovery and support checks

105 tests pass, including identity-bound restore, changed-field scope, incomplete-write restore, missing backup data, reduced hardware limits, private-data exclusion, malformed diagnostics, three role presets, server role rejection and a real Tk restore dialog rereading into the editor without writes. Library/history layout and compatibility dialog initialized offline at the minimum window size. No live device writes were performed. Repeater and Room Server profiles are reference-only; their CLI adapter and hardware validation remain future work. The user confirmed that updating 0.5.3 to 0.5.4 restarted successfully.

## 0.7.0 planning tools

116 tests pass. Added strict role-reply parsing and mocked serial/Companion identification, editable profile-note persistence, dry-run key exclusion and compatibility output, SQLite WAL-consistent backup, failed-backup preservation, and release-note extraction. Real Tk checks cover note editing, release text and library width. USB role detection is source-audited against official 1.17.1 CommonCLI and role definitions but still requires a live Repeater/Room Server bench test; no hardware writes were performed. Public community research is documented separately in COMMUNITY_REQUESTS.md.
