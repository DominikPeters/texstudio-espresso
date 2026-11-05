# TeXstudio Espresso

[![Live preview CI](https://github.com/DominikPeters/texstudio-espresso/actions/workflows/texpresso.yml/badge.svg?branch=main)](https://github.com/DominikPeters/texstudio-espresso/actions/workflows/texpresso.yml)

**TeXstudio Espresso** adds automatic live compilation and a native Qt preview
to [TeXstudio](https://github.com/texstudio-org/texstudio). It uses the same
pinned [TeXpresso engine](https://github.com/DominikPeters/texpresso) as the
[VSCode extension](https://github.com/DominikPeters/texpresso-vscode).
The engine is bundled with the application and uses your TeX installation for
packages. Each project retains its own session and preview position when
switching tabs. Normal TeXstudio build commands remain available for final PDFs.

[Website](https://pref.tools/texstudio-espresso/) · [Website deployment](site/README.md)

Open a saved `.tex` project to start. The preview includes continuous scrolling,
page navigation, zoom and magnification, source synchronization, hyperlinks,
Pause/Resume, Stop, Restart and Output controls. Command-click on macOS
(Ctrl-click on Linux) jumps from the preview to the source.
View → Show → Live Preview enables or disables automatic preview.
The shared toolbar switches between live preview and the compiled PDF.

## Builds and installation

- [Native build instructions](native/README.md)
- [macOS signed-build workflow](https://github.com/DominikPeters/texstudio-espresso/actions/workflows/texpresso-release.yml)
  and [signing/source-distribution instructions](native/MACOS_RELEASE.md)
- [Windows and WSL setup](native/WINDOWS.md)
- [Background testing and validation](native/TESTING.md)

Build workflows provide artifacts in GitHub Actions. Release downloads, when
published, are available on the [releases page](https://github.com/DominikPeters/texstudio-espresso/releases).

## Development and contributions

`main` is the TeXstudio Espresso development branch in this standalone product repository.
The complete TeXstudio history is retained so upstream updates can be merged.
[CONTRIBUTING.md](CONTRIBUTING.md) describes product contributions and the separate
[upstream-contribution fork](https://github.com/DominikPeters/texstudio).
See the [integration design and implementation status](docs/texpresso-integration.md)
for architectural background.

## Upstream and licensing

TeXstudio Espresso builds on TeXstudio's editor, PDF viewer and editing tools. The
[upstream project](https://www.texstudio.org),
[user manual](https://texstudio-org.github.io/getting_started.html), and
[contribution guide](https://github.com/texstudio-org/texstudio/wiki/Contribute)
remain useful references for the shared functionality.

TeXstudio's original authors retain their attribution and license terms.
See [COPYING](COPYING), [distribution licensing](docs/distribution-licensing.md),
and the generated Licenses and Source inventory for the bundled engine and
third-party components.
