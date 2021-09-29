# vars-localize
Tool for creating localizations within the VARS database.

Author: Kevin Barnard ([kbarnard@mbari.org](mailto:kbarnard@mbari.org))

This project is made with [PyQt5](https://pypi.org/project/PyQt5/).

## Dependencies
Dependencies are managed primarily through Anaconda. Instructions for direct pip installation are listed below as well.

*Note: These instructions are designed for macOS or Linux users.*

### Using Anaconda
To setup the app within an Anaconda environment, follow the proceeding steps:

**1. Create environment**

From the root directory, run:
```bash
conda env create -f environment.yml
```

This will create an Anaconda environment named *vars-localize* with all required dependencies.

**2. Activate Anaconda environment**

To activate the environment, run:
```bash
$ conda activate vars-localize
```

### Using pip directly
If setup with Anaconda does not work or isn't preferred, the dependencies can be installed through pip3 with Python 3.

Run the following command to install the required packages in your system.
```bash
$ pip install -r requirements.txt
```

## Configuration **(required)**

### 1. Set the Annosaurus API key
Setting the API key is necessary for the application to save localization data back to VARS. 
Change this in `.env`:
```
API_KEY=foo
```

Production Annosaurus API keys may be acquired from Brian Schlining ([brian@mbari.org](mailto:brian@mbari.org)).

### 2. Configure the proper M3 endpoints
The application settings can be configured within `config/config.ini`.
The settings below should be modified to switch from test to production mode:
```ini
user_site = %(test_user_site)s/accounts/v1
anno_site = %(test_anno_site)s/anno/v1
kb_site = %(test_kb_site)s/kb/v1
vam_site = %(test_vam_site)s/vam/v1
```
To do this, simply replace all instances of `test` with `prod` *in this block only*.

## Usage

To start the application, run the following from the project directory:
```bash
python vars-localize.py
```

Once the application launches, log in with your VARS username.

Search for a concept in the bar at the top left of the application, then select a concept from the list of results to populate a tree of imaged moments in the pane below. 
Select an observation from the children in the subtree of the imaged moment, and draw a bounding box around the observed concept by clicking and dragging.

You can double-click on any created localizations to pull up a dialog of properties. Here, you can change the observation's concept, modify the localization bounds, or delete the localization. 
Additionally, localizations can be resized by dragging the corners of the box when this dialog is closed.