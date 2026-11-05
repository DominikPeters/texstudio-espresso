# Website publication

The static files in this directory are served at
<https://pref.tools/texstudio-espresso/>. No build step is needed.

The main download button recommends a binary for the browser's OS. CPU
architecture Client Hints distinguish Apple Silicon from Intel and Linux ARM64
from x64 when available. Without those hints, Macs default to Apple Silicon and
Linux uses explicit ARM platform/user-agent tokens or defaults to x64. The
legacy `MacIntel` platform and `Intel Mac OS X` user agent do not identify an
Intel CPU. Architecture requests time out after 250 ms or fall back on rejection.
Mobile and unrecognized browsers, and visitors without JavaScript, get the
GitHub release page. A separate GitHub link always provides all releases.

The **Deploy website** GitHub Actions workflow publishes changes to `site/` on
`main`. It can also be run manually, with an optional dry run. Pull requests
validate the page and its local image references without accessing FTP secrets.

Deployment uses repository Actions secrets `FTP_USERNAME` and `FTP_PASSWORD`,
server `w008ef9a.kasserver.com`, port 21, and the same FTP action as the TikZ
Editor website. The FTP account starts at the `pref.tools/` root: the destination
must be `texstudio-espresso/`, never `/` or `pref.tools/texstudio-espresso/`.
Only this site's tracked files are synchronized; a clean-slate deletion is not
used. Markdown documentation is excluded from uploads. The workflow checks the
published HTML and images against the committed bytes over HTTPS.

Local server inspection is available through `ssh kas`. The corresponding
document root is `/www/htdocs/w008ef9a/pref.tools/texstudio-espresso/`.
