# Changelog

## Reliable manual contact import — 0.7.7

- Fleet contact copying now accounts for firmware discovery filters. The app
  temporarily enables only the required contact types, imports and verifies
  one card at a time, then restores and verifies the original discovery flags.
- Serializing each import prevents the firmware's single pending advert slot
  from being overwritten by a rapid multi-card batch.

## Fleet contact library — 0.7.6

- Full device reads now collect the radio's signed MeshCore contact card and keep
  it in the portable `User Data/data` folder. A Contacts page shows both the
  current radio's contact table and every configured radio learned by the app.
- Current contact lists export to human-friendly CSV or structured JSON.
- Batch editor → More → Add fleet contacts reviews selected cards against each
  target, skips the target itself and existing contacts, checks device capacity,
  writes sequentially, and rereads each contact table for verification.
- Stored cards are checked for valid advert structure and a matching public
  identity before use. Contact reports and the fleet library remain local and
  are included in portable backups, never support reports.

## Network transport and custom-firmware support — 0.7.5

- Bounded, ordered TCP receive handling; awaited disconnect and task cleanup.
- Wi-Fi setup rechecks radio identity after saving and protects pending edits.
- Malformed network addresses/status types are rejected consistently.
- Regression coverage includes real loopback sockets, fragmented/coalesced
  responses and 350-contact sync. See BUG_AUDIT_2026-09-15.md.
- Promotes the capability-gated V4 Wi-Fi/tuning, T1000 motion GPS and T114
  display controls developed in 0.7.3–0.7.4. Unsupported controls stay disabled.

## Development only — 0.7.4-dev

- V4 Wi-Fi setup and TCP connections; passwords stay out of app profiles/reports.
- Advanced receive-delay and airtime tuning with paired write/read-back checks.

## Development only — 0.7.3-dev

- T1000 buzzer/LED/USB options and motion GPS presets; T114 display options.
- These capability-gated firmware extensions are independent of stable 0.7.0.

## Planning and portability — 0.7.0

- Help → Detect firmware role queries USB server firmware using read-only `get role` and identifies Companion via its protocol handshake. Unknown replies remain unknown. Server settings are still read-only references pending a full CLI adapter and hardware validation.
- Saved profiles now have editable user notes, preserved across updates/renames and JSON library import/export. Built-in presets remain read-only; make your own Companion profile to add notes.
- Export dry runs from Help (single device) or Batch editor → More. Reports show proposed settings, individual overrides and compatibility blocks using the last device reads. No writes or channel keys are included; names and locations can be present.
- Help → Back up portable app creates a verified ZIP containing saved profiles, preferences, snapshots, recovery reports, logs and a consistent SQLite history copy. Packaged builds also include the EXE. Download caches/old installers are excluded. Backups contain private data and belong outside support issues.
- App updates shows release notes before installing. Future release notes use this changelog rather than only generated commit summaries.
- Added COMMUNITY_REQUESTS.md with cited Reddit/forum findings and an unapproved suggested backlog. Community suggestions were not automatically implemented.

## Recovery, support and profiles — 0.6.0

- History can restore the fields/channels changed by a previous operation, including an incomplete write. It rereads the same radio by public identity, loads original values into the editor, and requires normal review, write and verification. Missing backups or incompatible current capabilities block restoration.
- Added bounded structured error logs and a support ZIP under Help. Exports contain app/system metadata, capability names and sanitized diagnostic categories/stack locations; they exclude names, keys, coordinates, identifiers, raw payloads and exception messages.
- Help → Report a bug on GitHub saves the ZIP and opens a prefilled issue. The user attaches the ZIP and submits it; no token or automatic upload.
- Added per-radio compatibility details for mixed hardware before batch naming/review. Unsupported fields/slots and validation failures block applying rather than silently dropping settings.
- Added three read-only built-ins: Companion starting point, Repeater setup reference and Room Server setup reference. Server references are preview/export only: their separate CLI transport is not implemented. They cannot be applied/imported as Companion profiles. Network radio settings, credentials and identity remain deployment choices.
- User confirmed the 0.5.3 → 0.5.4 automatic update/restart worked.

## Update restart test — 0.5.4

- Version-only test release to validate automatic update and restart from 0.5.3. No application behavior changes.

## Windows update restart — 0.5.3

- Restart with a fresh PyInstaller runtime so the updated EXE does not reuse temporary files removed when the old app exits.
- Added a real one-file packaged self-update probe; replacement and relaunch passed with a new, existing runtime directory. All 94 unit tests pass.
- Updating from an older version can still require one manual reopen because the old updater performs that restart.

## Public repository updates — 0.5.2

- Removed the updater token field, environment-token lookup and authorization headers. Public release checks and downloads require no sign-in.
- Updated missing-release/rate-limit messages and reduced the dialog height.
- Validation: 94 tests pass; anonymous public release lookup and executable download passed SHA-256 verification. Packaged startup passed.

## Thorough bug hunt — 0.5.1

- Replaced direct report/snapshot writes with atomic, flushed saves; shared atomic saving also protects profiles/preferences and serializes in-process writers. Failed saves retain the previous complete file.
- Preference-write errors no longer prevent closing. Theme callbacks are coalesced/cancelled during shutdown.
- Read-back now rechecks public identity and every requested channel, including unchanged channels; cleanup errors retain the primary connection error and cleanup has bounded waits.
- Update staging files are unique; staged digest is checked again before helper launch and after exit. Busy updates block parent shutdown; duplicate dialogs are prevented and failed downloads can be retried.
- Real Windows helper testing exposed an unavailable PowerShell checksum cmdlet; replaced it with .NET hashing and deterministic UTF-8 logs.
- Reject newer SQLite schema versions without rewriting them; reject boolean profile versions, oversized numeric input, malformed tokens and invalid asset metadata. Token errors never echo the credential.
- Validation: 94 tests pass, plus the real disposable Windows helper test for waiting, replacement, restart, backup and data preservation. Packaged startup checked separately. No hardware writes. Authenticated GitHub end-to-end update, live BLE, multi-radio writes and power-cycle persistence remain unvalidated.

## Documentation and repository cleanup — 2026-09-09

- Rewrote the README around the current portable app and simplified batch controls; removed obsolete button names, duplicated instructions and superseded test counts.
- Consolidated architecture/handoff notes and added VALIDATION.md with confirmed checks and outstanding hardware/update validation.
- Removed duplicate ignore rules. Documentation-only maintenance; no application version bump or portable EXE replacement.

## Portable app, appearance and GitHub updates — 0.5.0

- Portable EXE with adjacent User Data; hidden supporting folder keeps the executable prominent. Local handoff includes copies of existing snapshots/reports and the latest desktop history.
- Light/Dark/System choice, saved window placement, clearer text/symbol status indicators and battery symbols before advice. Theme covers settings, batch dialogs, text and comparison tables.
- Explicit GitHub release check/download/install with private-repository token entry, SHA-256 validation, cross-host credential stripping, previous-EXE backup and deferred replacement after exit. Tokens are never stored or bundled.
- Added Windows release workflow triggered by version updates; publishes EXE and portable ZIP after tests. Live private-release download/install needs authentication and a published newer release to validate end to end.

## Batch bug hunt — 2026-09-09

- Fixed newly saved shared profiles missing from the batch picker; saving now refreshes the list and active name. Loading rechecks the library and reports removed/unreadable profiles clearly.
- Marked edited shared settings in the picker so they are not mistaken for an unchanged saved profile.
- USB Find now removes disconnected ports and their stale snapshots while retaining Bluetooth discoveries. New row IDs remain unique after removals.
- Added a device-list scrollbar for larger fleets and keyboard focus when clicking device checkboxes.
- Duplicate selection notifications no longer discard a valid review; actual checkbox changes still invalidate it.
- Validation: 75 tests passed, including failed-port read continuation, refresh/identity-row handling, profile changes, selection guards and existing stop/failure checks. No hardware writes; live BLE and multi-radio writes remain unvalidated.

## Batch editor cleanup — 2026-09-09

- Consolidated discovery into a header transport picker with Find and Read. Newly discovered devices are checked by default; Read tries all checked connections and continues past read failures.
- Added per-device checkboxes and a master checkbox; selection is locked during operations.
- Added a saved-profile picker for shared settings and naming defaults. Personal names and coordinates remain in the individual step.
- Kept Edit shared and Compare visible; moved naming and saving into More. Review and Apply sit beside a smaller labeled review/results area.
- Validation: 71 tests pass, including checkbox behavior, profile scope and minimum batch-window layout. Packaged executable startup passed. No hardware writes.

## Equal columns on settings pages — 2026-09-09

- Applied equal-width columns to Device & radio, Location & GPS, Contact discovery and Telemetry. Device values and setting labels now wrap, removing the fixed-width truncation. Suggestions and battery symbols share a reserved column.
- Validation: 70 tests pass; all four populated pages fit at 1100x800 and 1920x1032, including long choice labels. Rebuilt the Windows executable.

## First-page cleanup and Windows executable — 2026-09-09

- Added a standalone windowed Windows executable with bundled Python and dependencies; packaged user data lives in LocalAppData.
- Expanded Device & radio suggestions with larger, wrapping text and reserved space for battery symbols; other pages retain their layout.
- Fixed bundled Tcl/Tk initialization order during executable launch testing.
- Validation: 70 automated tests passed, including minimum-window layout. Packaged startup opened all 23 settings and initialized history. No radio writes.

## Fleet workflow — 2026-09-09

- Added profile previews and side-by-side comparisons with missing-value and differences-only views; channel keys remain hidden.
- Added per-profile naming prefixes and starting numbers, preserved through JSON import/export.
- Added local SQLite history, recognition by public identity across connection changes, per-device progress and CSV result exports. Profiles remain JSON.
- Added read-only verification against saved expectations after a user-confirmed radio restart. Restart confirmation and reread results are recorded separately.
- Added pending-edit discard prompts and reserved space for batch progress/stop controls at the minimum window size.
- Validation: automated persistence, comparison, naming, failure, identity and restart-check tests; live hardware writes, restart persistence and Bluetooth remain pending bench validation.

## Bug hunt â€” 2026-09-09

Fixes shipped in commit [af76e77](https://github.com/TheIlluminate92/meshcore-configurator/commit/af76e77c4efd105498f83d479bc29c6c26e5f234).

### Fixed

- **Battery hint crashes:** typing non-finite numbers such as `NaN`, `inf`, or `1e999` could throw an error while updating the power-cost display. The hint now hides for those inputs; configuration validation still rejects them.
- **Unexpected shared settings:** reopening a channels-only profile or an intentionally empty shared selection could select radio settings automatically. The batch editor now preserves the chosen scope.
- **Profile library loading:** malformed profile names could break sorting and prevent the library from opening. Invalid names and identifiers are now listed as unreadable files, leaving valid profiles usable and the files untouched.
- **Profile updates changing scope:** updating a saved profile could add unrelated channel slots or omit settings unavailable on the current device. Updates now retain the existing channel-slot scope and refuse to silently drop unread settings or slots.
- **Batch channel staleness:** profile channels that already matched at review were omitted from the checks before writing other changes. All included profile channels are now checked for changes since review before a batch device is written.
- **Local Bluetooth dependency loading:** the installed Bluetooth package was inaccessible on the development PC. A fresh local copy was extracted, and the launcher now prefers `bluetooth_libs/` when available. Downloaded dependencies remain outside Git; normal Windows setup installs them from `requirements.txt`.

### Validation

- All **60 automated tests passed**, including new regression cases for these failures.
- A read-only T114 check returned **22 settings and 40 channel slots**, with **zero read errors**.
- No hardware settings were written during the bug hunt.

### Still needs validation

- Windows reports Bluetooth scanning unavailable/off on the development PC. A live BLE connection and configuration write remain untested.
- Real multi-device writes and persistence after restarting the radios still require bench testing.
