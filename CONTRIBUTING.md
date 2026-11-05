# Contributing to TeXstudio Espresso

## Repository layout

- `DominikPeters/texstudio-espresso` is the standalone product repository.
  Its default branch, `main`, contains Espresso development, CI and releases.
- `DominikPeters/texstudio` remains a GitHub fork of `texstudio-org/texstudio`
  for preparing upstream contributions. Existing branches and pull-request
  references remain there.
- `texstudio-org/texstudio` is the upstream TeXstudio project.

The Espresso repository preserves the shared Git history. Keep an upstream
remote and merge suitable upstream updates into `main`. The repository does not
need GitHub's fork relationship to merge that history.

The development checkout uses these remotes:

```text
origin         https://github.com/DominikPeters/texstudio-espresso.git
contributions  https://github.com/DominikPeters/texstudio.git
upstream       https://github.com/texstudio-org/texstudio.git
```

## Espresso changes

Create a focused branch from `origin/main`, then open a pull request targeting
Espresso's `main`. File Espresso-specific issues in the product repository.
Follow [the background testing instructions](native/TESTING.md) and the local
app/update rules in [AGENTS.md](AGENTS.md). Keep the pinned engine revision and
its runtime bundle consistent; see [native/README.md](native/README.md).

## Upstream TeXstudio changes

Prepare generic fixes on a clean branch based on `upstream/master`, push that
branch to `contributions`, and open the pull request against
`texstudio-org/texstudio`. Cherry-pick a self-contained Espresso fix onto that
branch when appropriate, and include its relevant tests and comparison evidence.
This keeps upstream pull requests focused on the generic change.

Use a separate checkout or Git worktree for upstream work when the Espresso
checkout has active builds. Follow upstream's own contribution instructions in
that checkout. The existing `fix/pdf-toolbar-dpi-scaling` branch is an example
of an upstream-focused contribution.

## Product CI and signing

The product repository owns live-preview CI, Windows/WSL validation and manual
signed macOS builds. The manual macOS workflow builds the selected product
revision using the reusable workflow in the same repository and commit.
Signing and notarization credentials are repository Actions secrets; secret
values must never be committed or printed in logs.
