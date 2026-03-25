# Screenshot Capture Guide

This guide explains how to capture and place screenshots for all placeholders in this documentation set.

## Capture Standards

Use these standards for consistency:

- Resolution target: 1920x1080 desktop capture.
- App window size: keep stable across all shots.
- Theme: pick one (light or dark) and keep consistent.
- Data hygiene: redact usernames, URLs, or sensitive IDs.
- File format: PNG.

## Where To Put Images

Store screenshots under:

- `docs/images/screenshots/`

Every placeholder in the docs references a file in that directory.

## Naming Convention

Use the exact filenames already referenced in placeholders (examples):

- `app-main-window.png`
- `search-panel-after-query.png`
- `entry-browser-selection.png`
- `image-canvas-new-box.png`
- `settings-sam3-tab.png`
- `sam3-candidate-controls.png`

## Capture Workflow (Recommended)

1. Launch app with deterministic test data.
2. Open one docs page and locate its placeholder filename.
3. Capture the exact UI state.
4. Save image using that exact filename in `docs/images/screenshots/`.
5. Refresh MkDocs preview and verify rendering.

## Linux Capture Options

Use one of these methods:

- GNOME screenshot app (`gnome-screenshot`).
- Flameshot (`flameshot gui`).
- Spectacle (KDE).

Example command:

```bash
gnome-screenshot -w -f docs/images/screenshots/app-main-window.png
```

## Shot List By Priority

Start with these high-impact screenshots first:

1. `app-main-window.png`
2. `login-dialog-initial.png`
3. `search-panel-after-query.png`
4. `entry-browser-selection.png`
5. `image-canvas-new-box.png`
6. `properties-dialog-open.png`
7. `settings-general-tab.png`
8. `settings-sam3-tab.png`
9. `sam3-candidate-controls.png`
10. `status-bar-fields.png`

## QA Checklist Before Commit

- Filenames exactly match placeholder links.
- No broken image icons in docs preview.
- Text in screenshots remains readable.
- No sensitive data exposed.
- Similar scale and framing across pages.

## Build/Preview Docs Locally

If MkDocs Material is installed:

```bash
uv run mkdocs serve
```

Then open the local URL shown in terminal and verify each page.
