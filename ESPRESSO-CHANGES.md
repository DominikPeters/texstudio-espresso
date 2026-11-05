# TeXstudio Espresso modifications

This is a modified TeXstudio distribution developed by Dominik Peters and
contributors, beginning in October 2026. It is an unofficial fork. The source
revision in each application identifies the exact version and supplied source
archive. Original copyright and license notices remain applicable.

Changes through 2026-11-05 include:

- Bundled TeXpresso live compilation using the user's TeX Live or MiKTeX installation,
  with a native Qt preview sharing TeXstudio's PDF controls and tools.
- Shared live/PDF panel, project sessions, scrolling, hyperlinks, SyncTeX,
  magnification, zoom, lazy page counts, incremental images and prewarming.
- Compiler auxiliary/bibliography handling, diagnostic integration, error
  recovery, bounded caches and worker lifecycle protection.
- Figure bounds and a hover action for opening supported TikZ figures in a
  locally installed TikZ Editor.
- Native Windows Qt client with WSL2 compilation and TeX setup, plus native
  macOS and Linux packaging with architecture-specific runtime requirements.
- Product versioning and updates from the standalone TeXstudio Espresso
  repository, with release builds and matching sources for all three platforms.
- Memory/performance fixes and background protocol/editor regression testing.
- Compressed dictionaries, compact renderer packaging, an adapted cup icon and
  splash, and an isolated persistent development app.
- Distribution inventories, original third-party notices, per-payload dictionary
  provenance, accessible license/source information, and corresponding-source
  packaging with matching dependency archives, patches and build recipes.

The engine fork contains modifications adapted from texpresso-vscode and local
engine work. Its exact source is included separately at the recorded submodule
revision, together with its own original and third-party notices. This document
does not change any component's license or claim upstream endorsement.
