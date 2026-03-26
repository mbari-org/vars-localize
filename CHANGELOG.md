# CHANGELOG


## v0.4.0 (2026-03-26)

### Features

- Add logo to app & docs, post-install command for Desktop file (Linux)
  ([`ee9c8d8`](https://github.com/mbari-org/vars-localize/commit/ee9c8d89ccbfefe4f3c5f9900220b1591f7df05d))


## v0.3.0 (2026-03-25)

### Chores

- Remove CLIP from sam extra requirements
  ([`ca0e2a2`](https://github.com/mbari-org/vars-localize/commit/ca0e2a255cbb4d5429f29113205729a1e86f615d))

### Documentation

- Add main window screenshot
  ([`a3c2a85`](https://github.com/mbari-org/vars-localize/commit/a3c2a8529e5c28b5027f934b439ef4fbcceada69))

- Fix links, add note about SAM3 download
  ([`576380d`](https://github.com/mbari-org/vars-localize/commit/576380de65bf5b5b61bfbbc43b417664446cbb30))

### Features

- Add video sequence name handling and caching in M3Service and UI components, minor bugfixes
  ([`b1aa00e`](https://github.com/mbari-org/vars-localize/commit/b1aa00ec3fcea29e3db315c28670c227c71e6917))


## v0.2.0 (2026-03-25)

### Chores

- Add pre-commit and python-semantic-release + GH action
  ([`8a9fbe6`](https://github.com/mbari-org/vars-localize/commit/8a9fbe685b9fc9a898d9972fc6d243e2fe5e845e))

- Fix pyproject.toml path
  ([`863de78`](https://github.com/mbari-org/vars-localize/commit/863de78bd57397f081de944029e97800f623c921))

- Pin semantic release version in CI/CD workflow
  ([`5c7e1bb`](https://github.com/mbari-org/vars-localize/commit/5c7e1bb5f5f8d2da941c04bc4df32b2db7ac1772))

- Update semantic release changelog configuration
  ([`a6bfc59`](https://github.com/mbari-org/vars-localize/commit/a6bfc5965829f0e33fb73b74ec1a14650568da57))

- Update uv lock file
  ([`bb6aa04`](https://github.com/mbari-org/vars-localize/commit/bb6aa049c9c22425b791cdd340cc4826596f255a))

### Documentation

- Add basic docs
  ([`3e3a053`](https://github.com/mbari-org/vars-localize/commit/3e3a0532e304467179aa198bcfcf2cdf1d082f7f))

- Simplify readme, clarify Python 3.10+ required
  ([`6cfff68`](https://github.com/mbari-org/vars-localize/commit/6cfff686b387af49393d0a8b74815fb1d6c2021b))

### Features

- Add "Annotate Concept" combo box and fix logic to support 1 box per observation
  ([`f114a25`](https://github.com/mbari-org/vars-localize/commit/f114a250179b56d420af4c1822e243439793799d))

- Overhaul
  ([`8d1c800`](https://github.com/mbari-org/vars-localize/commit/8d1c80097b86a7cc50e96929f34808c4535a7e02))

- Tighten up overhaul implementation
  ([`ebc7bef`](https://github.com/mbari-org/vars-localize/commit/ebc7befedf85364b7fc2ffdc80bfd13168eb83de))

- **ui**: Enhance login dialog with username focus method
  ([`6f3875a`](https://github.com/mbari-org/vars-localize/commit/6f3875a60c77ab6306dfd1b69d6c6d73c8781384))

feat(ui): improve search panel with loading state management and request handling

fix(async): update error handling in async worker to emit exceptions correctly

refactor(utils): normalize bounding box extraction to yield dictionaries

test(tests): enhance client tests with typed error handling and response validation

test(tests): add tests for entry tree refresh logic and image view SAM functionality

test(tests): implement race condition tests for search panel loading behavior


## v0.1.0 (2024-12-09)

### Bug Fixes

- Add workaround for changed vam endpoint
  ([`dc069a4`](https://github.com/mbari-org/vars-localize/commit/dc069a4a4aad4e4df0d7f399a43883b14028ec48))

- Correct SearchPanel behavior and saveability
  ([`7fd14c6`](https://github.com/mbari-org/vars-localize/commit/7fd14c619983bd48397eb2be00c6daa17f11555b))

- Add set_dialog_saveable function to enable/disable save button - Connect concept_field signals to
  update saveability - Only rename observation if dialog is accepted

- Fall back on jpeg image references when no png found
  ([`6644a4e`](https://github.com/mbari-org/vars-localize/commit/6644a4e3d121f1ed5b3267d1e93b3585e910f3c2))

- Fix crash on key press in imaged moment tree
  ([`3c1f870`](https://github.com/mbari-org/vars-localize/commit/3c1f870b3d78957017251ca5e5bc2f4709240068))

- Grab focus in login dialog
  ([`4407edb`](https://github.com/mbari-org/vars-localize/commit/4407edb7329937fc2b00bf3b8298b0298a251413))

- Handle empty string in n_split_hash function
  ([`84288ca`](https://github.com/mbari-org/vars-localize/commit/84288ca6361f4675750cf3142f7804d73d3cb045))

- Remove defunct time windowing
  ([`9870590`](https://github.com/mbari-org/vars-localize/commit/987059079fe0d8e210749ea13c8d272fe2df8126))

- Remove unused .env and supporting code
  ([`7819fcf`](https://github.com/mbari-org/vars-localize/commit/7819fcf9c0313a5825c0021af8112b11942fbb15))

- Remove unused strength map and bbox field
  ([`e99d74d`](https://github.com/mbari-org/vars-localize/commit/e99d74d87c8f64d2d83505849cdee57799c6bd80))

- Update default M3 URL to use HTTPS
  ([`054d817`](https://github.com/mbari-org/vars-localize/commit/054d817cec6025eae86d76d798d7f2459590cf21))

- Update recorded_date -> recorded_timestamp for new Annosaurus
  ([`ad5fb5e`](https://github.com/mbari-org/vars-localize/commit/ad5fb5ec41366942a53af8682b537370ea3a7f6a))

### Chores

- Remove unused config.ini
  ([`1d26818`](https://github.com/mbari-org/vars-localize/commit/1d268187b0d7865a1eb8588a9fe22bcfdc9f2439))

- Rework project structure for Rye
  ([`75b08c8`](https://github.com/mbari-org/vars-localize/commit/75b08c8dd9cbeb5589fb20ef2d9a35ba81c09a54))

### Features

- Draw uneditable video-made bounding boxes
  ([`b098529`](https://github.com/mbari-org/vars-localize/commit/b098529edf1199fefe01ced730bbabf62ed24c4c))

- Remove filter on bounding box associations in assocation list, add splitter to customize UI size
  ([`4dd816c`](https://github.com/mbari-org/vars-localize/commit/4dd816cc98c09177e50978cde65b9b24c15e0326))

- Support alternative M3 url via CLI
  ([`6fe9820`](https://github.com/mbari-org/vars-localize/commit/6fe98207311feb5e55eda75f07490cc7436da25d))
