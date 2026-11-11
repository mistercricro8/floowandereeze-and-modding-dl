# Automatic GUI screenshots

The root-level `capture_docs.py` follows the screenshot workflow in `floo-qt`:
it opens the real PySide6 window, switches tabs, selects real game assets, prepares
image previews, and saves PNGs. It also captures the character asset dialog.

## Prepare and run

Configure a downloaded Duel Links account in the app and click **Check** to populate
`database.db`. Close the game. From the project root, sync the runtime dependencies
and rebuild generated Qt modules before capturing:

```bash
uv sync
uv run floo-build-qt
uv run floo-capture
```

The default command replaces `config.png`, `sleeve.png`, `card.png`, `field.png`,
`character.png`, `character_edit.png`, and `backups.png` in `docs/assets/ui/`.
It prints each destination and writes the Qt version, window mode, selected asset
names, and image dimensions to `build/docs-captures/manifest.json`.

The window maximizes by default and switches tabs automatically. Let it finish
without interacting with it. Captures include the application contents, without
the operating system's title bar or desktop. Qt captures at the screen's pixel density.

## Choose pages and output

```bash
uv run floo-capture -- --pages character --character-search "Yugi"
uv run floo-capture -- --pages card sleeve --card-search "Blue-Eyes"
uv run floo-capture -- --database local/development.db --output build/review-captures
uv run floo-capture -- --windowed --width 1600 --height 1000
uv run floo-capture -- --offscreen --output build/headless-captures
```

`--pages` accepts `config`, `sleeve`, `card`, `field`, `character`, and `backups`.
The character option saves both the page and its asset dialog. Card search defaults
to `Blue-Eyes` and requires at least three characters. Characters use the first
result, optionally narrowed by `--character-search`; other editors select the first
metadata result. The character dialog selects the first asset with a readable texture.
Missing metadata or installed textures fail the run instead of creating placeholder
previews. Earlier captures can remain after a failure.

`--windowed` uses the requested logical dimensions (minimum 1280 × 900).
`--offscreen` also uses fixed dimensions and renders without displaying a window;
platform fonts and styles can differ from normal Windows captures.
Configuration and Backups can be captured without a game path:

```bash
uv run floo-capture -- --pages config backups --offscreen
```

## Isolation and review

The helper opens the source SQLite database read-only and uses SQLite's backup API
to make a consistent temporary copy under `build/`. Application migrations and
configuration callbacks affect only that copy. Qt settings and temporary images
are isolated in the same disposable directory. It reads the project's real backup
inventory for display. It never invokes Replace, Restore, Check, Import, or Remove.

Configuration displays generic account and local metadata paths and clears the custom background;
the actual game path remains available internally for reading textures. Review
screenshots before publishing: metadata source settings, backup filenames, and
asset names reflect your local data. Installed mods and missing game downloads
also affect the pictures.

The editor source previews reuse their selected installed artwork through the normal
image-loading handler. Current and replacement previews intentionally show the
same artwork; no mod is applied. Example images are removed with the temporary copy.

To review separately before replacing documentation pictures:

```bash
uv run floo-capture -- --output build/review-captures
# Inspect the PNGs, then copy the reviewed pictures.
cp build/review-captures/*.png docs/assets/ui/
uv run --group docs mkdocs build --strict --site-dir build/docs-preview
```

When `--output` is supplied, its manifest is saved alongside its PNGs.
