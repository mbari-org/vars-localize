# vars-localize
Tool for creating localizations within the VARS database.

Author: Kevin Barnard ([kbarnard@mbari.org](mailto:kbarnard@mbari.org))

## :hammer: Installation

> [!NOTE]
> VARS Localize requires Python 3.8 or later.

To install VARS Localize, run:
```bash
pip install vars-localize
```

## :rocket: Usage

To start the application, run:
```bash
vars-localize [-u URL]
```

Once the application launches, log in with your VARS username and password.

Search for a concept in the bar at the top left of the application, then select a concept from the list of results to populate a tree of imaged moments in the pane below. 
Select an observation from the children in the subtree of the imaged moment, and draw a bounding box around the observed concept by clicking and dragging.

You can double-click on any localization to edit its properties in a dialog.
Additionally, a localization can be resized by dragging the square corners of its bounding box.

## Credits

VARS Localize is made with [PyQt6](https://pypi.org/project/PyQt6/).

---

Copyright &copy; 2019 [Monterey Bay Aquarium Research Institute](https://www.mbari.org/)