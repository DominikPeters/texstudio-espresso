# Website publication

The static files in this directory are served at
<https://pref.tools/texstudio-espresso/>. No build step is needed.

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
