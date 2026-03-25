# Architecture

This page summarizes the app architecture to support maintenance and extension.

## High-Level Layers

- `ui`: PyQt widgets and user interactions.
- `services`: M3/SAM3 service integration and backend operations.
- `state`: app-level state and settings.
- `models`: data entries and hydration helpers.
- `util`: logging, async helpers, and utility functions.

## Main Runtime Flow

1. Entry point creates `QApplication` and `AppWindow`.
2. `AppWindow` performs login and service configuration.
3. `SearchPanel` loads concepts and query results.
4. `ImagedMomentTree` coordinates moment/observation selection.
5. `ImageView` handles image rendering, box interactions, and optional SAM3.

## Key UI Components

- `AppWindow`: shell, menu, status, and wiring.
- `SearchPanel`: query modes, controls, pagination.
- `ImagedMomentTree`: synchronized tabular browser.
- `DisplayPanel`: SAM status/controls and image view.
- `ImageView`: graphics scene and localization logic.
- `SettingsDialog`: tabbed app configuration.

## State Signals

`AppStateStore` signals synchronize user, loading, concept, and result count state across panels.

## Async Operations

`run_async` is used for non-blocking service calls, including:

- concept list loading
- image fetch
- video metadata fetch
- SAM3 candidate operations

## Permissions and Modes

- Normal users edit owned observations.
- Privileged roles can toggle Admin Mode from Options.

<!-- ### Screenshot Placeholder: Admin Mode Warning Dialog

![Admin mode warning placeholder](../images/screenshots/developer-admin-mode-warning.png) -->
