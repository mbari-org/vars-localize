# vars-localize
Tool for creating localizations within the VARS database.

Author: Kevin Barnard ([kbarnard@mbari.org](mailto:kbarnard@mbari.org))

## :hammer: Installation

> [!NOTE]
> VARS Localize requires Python 3.10 or later.

To install VARS Localize, run:
```bash
pip install vars-localize
```

To install with local SAM3 assist support, run:
```bash
pip install "vars-localize[sam]"
```

Note that SAM3 support requires additional model setup; see the [SAM3 Assistance](https://docs.mbari.org/vars-localize/user-guide/sam3-assistance.md) documentation for details.

## :rocket: Basic Usage

To start the application, run:
```bash
vars-localize
```

Once the application launches, enter your M3 URL, then log in with your VARS username and password.

For complete setup, workflows, UI guidance, and SAM3 details, see:

- https://docs.mbari.org/vars-localize

## Credits

VARS Localize is made with [PyQt6](https://pypi.org/project/PyQt6/).

---

Copyright &copy; 2019 [Monterey Bay Aquarium Research Institute](https://www.mbari.org/)