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

Use a conventional public release layout: platform binaries, checksums and a
short source/build-information section. Mac downloads are signed, notarized DMGs
with the coffee-cup icon and an Applications shortcut. Link the editor and engine
at the exact shipped commits, and provide `source-manifest.json` with the exact
upstream dependency URLs, versions and hashes. `source-info.zip` contains only
small build metadata: original recipes, patches and configuration.
GitHub also supplies the standard project source archives; explain that a
recursive clone obtains the separately pinned engine submodule.

Do not publish dependency caches as individual assets or aggregate every
third-party source archive into a giant ZIP. Those are internal build inputs.
Source references must include applied modifications and remain accessible while
the corresponding binaries are distributed. Check links and repair/mirror any
input that disappears; generic upstream homepages or a moving main branch do not
identify corresponding source. See the [GNU FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites).

The Mac packaging helpers inspect final DMGs without opening Finder: the
shortcut, icon bytes, signatures, tickets and offscreen startup are checked.
Packaging-only corrections retain the original application source revision and
record the additional packaging revision separately.

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
platform assets, their download sizes and source/build-information links. Normal pushes deploy the static site
through the scoped FTP workflow described in `site/README.md`.
