# vars-localize
**VARS Localize** is a tool for creating and editing bounding box localizations for VARS annotations.

Author: Kevin Barnard ([kbarnard@mbari.org](mailto:kbarnard@mbari.org))

This project is made with [PyQt5](https://pypi.org/project/PyQt5/) and built with [Poetry](https://python-poetry.org/).

## Install

VARS Localize is available on PyPI as [vars-localize](https://pypi.org/project/vars-localize/) and can be installed with pip:

```
pip install vars-localize
```

Alternatively, if you want to build and install from source, you can use Poetry:

```
poetry install
```

## Usage

Once installed, you can use VARS Localize by running the following command:

```
vars-localize
```

Once the application launches, log in with your VARS username and password.

Search for a concept in the bar at the top left of the application, then select a concept from the list of results to populate a tree of imaged moments in the pane below. 
Select an observation from the children in the subtree of the imaged moment, and draw a bounding box around the observed concept by clicking and dragging.

You can double-click on any localization to edit its properties in a dialog.
Additionally, a localization can be resized by dragging the square corners of its bounding box.
