# Security policy

## Supported versions

Security fixes are made against the current stable release and the `main` branch. Update to the latest published release before reporting behavior that may already have been corrected.

## Reporting a vulnerability

Do not open a public issue with exploit details, credentials, channel keys, device identities, precise locations, private profiles, raw device traffic, or portable backups.

Use GitHub's **Report a vulnerability** option on this repository's Security tab when it is available. If private vulnerability reporting is unavailable, contact the maintainer through the GitHub profile without including sensitive details and ask for a private reporting channel.

Include only what is necessary to reproduce and assess the problem:

- affected app version and Windows version
- radio model, firmware version, and USB/Bluetooth/Wi-Fi transport
- a concise reproduction sequence
- expected and observed behavior
- likely impact and whether device writes occurred
- sanitized logs or a support ZIP created by the app, after reviewing it

Never include account credentials, radio private keys, channel keys, names, contact lists, coordinates, raw profiles, browser data, or a full `User Data` folder.

Please allow time for triage before publishing technical details. There is no guaranteed response time, but safety-impacting reports will be prioritized.

## Public bug reports

Ordinary bugs that do not expose sensitive information can use the repository's normal issue forms. Follow [SUPPORT.md](SUPPORT.md) and attach only the app-generated support ZIP after reviewing it.
