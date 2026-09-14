# Getting help

## Download and start

Use the [latest release](https://github.com/TheIlluminate92/meshcore-configurator/releases/latest), download **MeshCore-Configurator-portable.zip**, and extract the whole folder. Open **! MeshCore Configurator.exe**. Keep its hidden **User Data** folder beside it.

## Report a problem

Choose **Help → Report a bug on GitHub**. Save the support ZIP, describe what happened on the issue page, attach the ZIP and submit. GitHub may ask you to sign in. The app never uploads or submits automatically and needs no GitHub token.

You can also choose **Help → Save support report** and attach it to a [new issue](https://github.com/TheIlluminate92/meshcore-configurator/issues/new/choose). Include the app version, radio model/firmware, USB or Bluetooth, the steps you tried and the exact error message.

Support ZIPs omit names, identifiers, locations, channel keys, raw device payloads and exception messages. They contain app/system metadata, reported capability names and categorized diagnostics. Review screenshots yourself before sharing.

## Which file is safe to attach?

| File | Purpose | Sharing |
| --- | --- | --- |
| Support ZIP from Help | Diagnose an app problem | Designed for public issue attachment |
| Portable backup ZIP | Recover your app and saved data | Keep private; contains profiles and potentially keys, names, contacts and locations |
| Device snapshot or apply report | Configuration recovery and local review | Keep private |
| Saved profile JSON | Reuse selected settings/channels | Inspect before sharing; may include channel keys and personal notes |
| Dry-run JSON | Review a proposed change | Keys are omitted, but names and locations may be present |

## Common connection problems

If Windows says the USB port is busy or access is denied, close the browser, phone connection or other app using that radio, reconnect it, then read again. Bluetooth requires BLE-enabled Companion firmware. Unknown firmware is not assumed to be a supported device.

**Help → Detect firmware role** performs read-only discovery. Repeater and Room Server writes are not implemented yet; their built-in profiles are setup references.

## Recovery

**History → Restore previous settings** rereads the original radio and loads the values changed by a previous operation. Review and apply are still required. This does not restore firmware, private identity or contacts.

To restore a portable backup, close the app and extract the backup into a separate folder. Keep the previous folder until you confirm the recovered app and data work. A source-created backup needs a compatible portable EXE beside User Data.
