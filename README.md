# eGPU Game Config Swap

eGPU Game Config Swap is a Decky Loader plugin for SteamOS. A game can need different graphics settings when an eGPU dock is connected and when it is disconnected, but the game keeps the same configuration after the GPU changes. This plugin stores an "eGPU" profile and an "Internal" profile for each registered game, then lets you switch profiles with one button.

Only Proton games can be registered. Native Linux games are not currently supported. The plugin has been verified on SteamOS; Bazzite has not been verified.

## Install

Both installation methods require Decky Loader's Developer tab. Enable **Developer mode** in Decky Loader settings first; otherwise, the Developer tab is hidden.

Use either method:

1. **Local ZIP:** Download `gfxprofile.zip` using the fixed release URL below. In the Developer tab, select *Install Plugin from ZIP File*, then select the downloaded file.
2. **Release URL:** In the Developer tab, enter the fixed release URL under *Install Plugin from URL*.

```
https://github.com/kanonjeong-ops/gfxprofile/releases/latest/download/gfxprofile.zip
```

The URL always points to the latest release. Each release's notes include the SHA-256 checksum of `gfxprofile.zip`.

## Usage

See the [usage guide](USAGE.en.md) for operating instructions. A Korean version is available: [한국어 사용 설명서](USAGE.ko.md).

## Updates

There are no automatic updates, and the plugin does not notify you when a new release is available. To receive release notifications, use either option:

- On the GitHub repository, choose **Watch → Custom → Releases**.
- Subscribe to `https://github.com/kanonjeong-ops/gfxprofile/releases.atom` in an Atom feed reader.

## Data and removal

Registrations, saved profiles, and backups are stored in `~/homebrew/data/gfxprofile/`. Logs are stored in `~/homebrew/logs/gfxprofile/`.

To remove the plugin and its data, uninstall the plugin in Decky, then delete `~/homebrew/data/gfxprofile/`, `~/homebrew/logs/gfxprofile/`, and the empty `~/homebrew/settings/gfxprofile/` folder that Decky Loader creates.

## Support

Report problems through [GitHub Issues](https://github.com/kanonjeong-ops/gfxprofile/issues). Support is best-effort. Some problems cannot be reproduced without an eGPU dock.

## License

The plugin is released under the Unlicense and is in the public domain. The distribution includes third-party components; their notices are in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Attribution is not required. If you use or fork this project, attribution would be appreciated.

### About AI use

This plugin's code was written by AI — **Anthropic's Claude**, driven through
Claude Code, with **OpenAI's Codex CLI** used as an independent cross-reviewer.
