# TeXstudio Espresso releases

The product version is the upstream TeXstudio version followed by a fork revision,
for example **4.9.9-espresso-1**. Increment the fork revision for subsequent
releases of the same upstream base. `src/productversion.h` is the displayed
version source; Windows numeric file versions in `win.rc` must match it.
Upstream's own `Version` parser remains available for upstream functionality;
product update checks parse only published TeXstudio Espresso release tags.
Imported upstream Git tags are never offered as product updates.

Run **Prepare TeXstudio Espresso release** on `main` after committing the release
changes. Its reusable workflows build macOS arm64/Intel, Windows x64 with WSL2,
and Linux x64/ARM64 from the same commit. The final job runs only after all
platform jobs succeed. It checks every matching project source ZIP, engine
gitlink and dependency source hash, combines reusable dependency archives,
generates release notes/checksums, and creates a **draft** GitHub release.
Review the concrete draft and then publish it. The workflow does not install or
restart a local app. The macOS release candidates are Developer ID signed,
notarized and stapled; local development builds remain ad-hoc signed.

Each binary is accompanied by its matching `-sources.zip`. The separate
dependency sources are indexed in `dependency-sources-index.json` and `.html`;
GitHub's automatic source archive is not a replacement for the recursive project
source and exact dependency inputs. Preserve published source assets while the
corresponding binaries remain distributed. The per-platform manifests bind the
original package sources and checksums to the actually shipped package versions.

macOS requirements are derived from the maximum deployment target across all
shipped Mach-O code images and written to `LSMinimumSystemVersion` and
`runtime-requirements.json`. The current packaged Homebrew stack requires macOS
15.0; each new build repeats the audit. Linux packages declare actual shared
library dependencies and report the maximum required GLIBC symbol version.
They install below `/opt/texstudio-espresso` with a separate launcher/desktop
entry so upstream TeXstudio can remain installed. Windows uses an unsigned
portable ZIP and requires WSL2, plus TeX Live or MiKTeX inside the chosen
distribution. No distribution-name whitelist is imposed.

After publishing, update `site/index.html` with direct links to the released
platform assets and their source index. Normal pushes deploy the static site
through the scoped FTP workflow described in `site/README.md`.
