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

To install with local SAM3 assist support, run:
```bash
pip install "vars-localize[sam]"
```

## :rocket: Usage

To start the application, run:
```bash
vars-localize
```

Once the application launches, enter your M3 URL, then log in with your VARS username and password.

## Settings

Open settings from:

- Menu: `Options -> Settings...`
- Hotkey: `Ctrl+,` (customizable in settings)

Settings are organized into tabs:

- General: keyboard shortcuts and search page size
- Connection: default M3 URL and startup connection timeout
- SAM3 / AI: local model path and SAM3 tuning options

If you change the default M3 URL, it will prefill the next login dialog.

Search for a concept in the bar at the top left of the application, then select a concept from the list of results to populate a tree of imaged moments in the pane below. 
Select an observation from the children in the subtree of the imaged moment, and draw a bounding box around the observed concept by clicking and dragging.

You can double-click on any localization to edit its properties in a dialog.
Additionally, a localization can be resized by dragging the square corners of its bounding box.

### Optional SAM3 Assist

If installed with the sam extra, you can enable SAM3 assist in the Options menu:

- Option path: Options -> Enable SAM3 Assist
- Default: off
- Inference: local model execution on your machine
- Model file: required and configured in Settings -> SAM3 / AI

Important:

- VARS Localize does not download SAM3 model files automatically.
- You must download the model file yourself and set its local path in Settings.

When enabled:

- Image embeddings are prepared in the background when an imaged moment loads.
- Selecting an observation prompts SAM3 using the observation concept and proposes candidate boxes.
- Candidate boxes can be accepted/rejected with the check and x controls above the image.
- Candidate boxes that overlap existing boxes are filtered out using a conservative IoU threshold.
- Hovering the image proposes a point-prompted candidate box at the mouse location.
- Right-click applies the current hover proposal.
- Standard left-click drag to create boxes still works.

## Credits

VARS Localize is made with [PyQt6](https://pypi.org/project/PyQt6/).

---

Copyright &copy; 2019 [Monterey Bay Aquarium Research Institute](https://www.mbari.org/)