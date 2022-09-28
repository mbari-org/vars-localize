# vars-localize
Tool for creating localizations within the VARS database.

Author: Kevin Barnard ([kbarnard@mbari.org](mailto:kbarnard@mbari.org))

This project is made with [PyQt6](https://pypi.org/project/PyQt6/).

## Setup

Installation of requirements is managed either by Anaconda or pip.

### Using Anaconda (**recommended**)

#### 1. Create an environment

From the root directory, run:
```bash
conda env create -f environment.yml
```

This will create an Anaconda environment named `vars-localize` with all required dependencies.

#### 2. Activate the environment

To activate the environment, run:

```bash
conda activate vars-localize
```

### Using pip (Python >= 3.7)

To install the required Python packages in your active Python environment, run:

```bash
pip install -r requirements.txt
```

## Usage

To start the application, run:
```bash
python vars-localize.py
```

Once the application launches, log in with your VARS username and password.

Search for a concept in the bar at the top left of the application, then select a concept from the list of results to populate a tree of imaged moments in the pane below. 
Select an observation from the children in the subtree of the imaged moment, and draw a bounding box around the observed concept by clicking and dragging.

You can double-click on any localization to edit its properties in a dialog.
Additionally, a localization can be resized by dragging the square corners of its bounding box.