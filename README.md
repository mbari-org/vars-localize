# vars-localize

Tool for creating localizations within the VARS database.

## Dependencies

### Using Anaconda
To setup the app within an Anaconda environment, follow these steps.

#### 1. Create environment
From the root directory, run:
```bash
conda env create -f environment.yml
```
This will create an Anaconda environment named *vars-localize* with the python depedencies.

#### 2. Activate Anaconda environment
To activate the environment, run:
```bash
conda activate vars-localize
```

#### 3. Install the fman build system
With the environemnt activated, run:
```bash
pip install fbs
```

### Using pip directly
If setup with Anaconda does not work or isn't preferred, the dependencies can be installed through pip3 with Python 3.

Run the following commands to install the required packages in your system.
```bash
pip3 install PyQt5
pip3 install JPype1==0.6.3
pip3 install jaydebeapi
pip3 install fbs
```