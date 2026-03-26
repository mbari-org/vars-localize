# Installation

## Requirements

- Python 3.10+
- Access to an M3 instance
- Network access to required services (VPN if applicable)

## Install From PyPI

```bash
pip install vars-localize
```

## Install With SAM3 Support

```bash
pip install "vars-localize[sam]"
```

## Development Environment Install

If you are working in this repository:

```bash
uv sync
```

## Run The App

```bash
uv run vars-localize
```

or

```bash
vars-localize
```

## Verify Startup

You should see the login dialog first.

## Linux Desktop Entry (Optional)

To install a user-level desktop launcher and icons on Linux:

```bash
vars-localize install-desktop
```

To remove the desktop launcher and icons:

```bash
vars-localize uninstall-desktop
```

<!-- ### Screenshot Placeholder: Login Dialog On Startup

![Login dialog on startup placeholder](../images/screenshots/login-dialog-initial.png) -->

!!! tip
    If the login dialog does not appear, check terminal logs and review [Troubleshooting](../reference/troubleshooting.md).
