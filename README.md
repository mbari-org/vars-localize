# vars-localize
Tool for creating localizations within the VARS database. Tentatively named **VARS Anchor**.

This project is made with [PyQt5](https://pypi.org/project/PyQt5/) through the [fman build system](https://build-system.fman.io/).

## Usage

### Run from source
To run the application from source, run the following from the project directory:
```bash
fbs run
```
Once the application launches, log in with your VARS observer ID.

Search for a concept in the bar at the top left of the application, then select a concept from the list of results to populate a tree of imaged moments in the pane below. 
Select an observation from the children in the subtree of the imaged moment, and draw a bounding box around the observed concept by clicking and dragging.

You can double-click on any created localizations to pull up a dialog of properties. Here, you can change the observation's concept, modify the localization bounds, or delete the localization. 
Additionally, localizations can be resized by dragging the corners of the box when this dialog is closed.

## Configuration (required)
*The configuration directory is `src/main/resources/base/config/`. All files within this section are referenced from within this directory.*

Setting the API key is necessary for the application to save localization data back to VARS. Put the API key on a single line within the file `api_key.txt`.

The official M3 API key can be acquired from Brian Schlining ([brian@mbari.org](mailto:brian@mbari.org)).

The application settings can be configured within `config.ini`.
Specifically, the settings below should be modified to switch from test to production mode:
```ini
user_site = %(test_user_site)s/accounts/v1
anno_site = %(test_anno_site)s/anno/v1
kb_site = %(test_kb_site)s/kb/v1
vam_site = %(test_vam_site)s/vam/v1
```
To do this, simply replace all instances of `test_***_site` with `prod_site` *in this block*.

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
*Note: Windows users should use `environment_windows.yml` instead of `environment.yml`*

This will create an Anaconda environment named *vars-localize* with the python dependencies.

**2. Activate Anaconda environment**

To activate the environment, run:
```bash
conda activate vars-localize
```

**3. Install the fman build system**

With the environment activated, run:
```bash
pip install fbs
```

### Using pip directly
If setup with Anaconda does not work or isn't preferred, the dependencies can be installed through pip3 with Python 3.

Run the following commands to install the required packages in your system.
```bash
pip3 install PyQt5
pip3 install requests
pip3 install fbs
```

## Deployment
**Before deploying, first ensure that the proper configurations are set within `src/main/resources/base/config/`.** See the *Configuration* section for more details.

To generate an installer for the application, follow the steps below and run the following commands from the project directory.

1. Install `fpm` by following [these instructions](https://fpm.readthedocs.io/en/latest/installing.html).
2. Freeze and generate the installer:
```bash
fbs freeze
fbs installer
```

Additional information can be found in the [fbs manual](https://build-system.fman.io/manual/).