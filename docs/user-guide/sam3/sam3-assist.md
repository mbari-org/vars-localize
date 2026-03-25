# SAM3 Assist

SAM3 assist is optional and runs locally when enabled and configured.

!!! warning
    SAM3 assist requires significant local resources, including a compatible GPU with sufficient VRAM (8GB+ recommended). Performance may vary based on hardware capabilities.
    Before using SAM 3, please request access to the checkpoints on the [SAM 3 Hugging Face repo](https://huggingface.co/facebook/sam3).

## Enabling SAM3

1. Install with SAM extras.
2. Open Settings -> SAM3 / AI.
3. Enable SAM3 and provide a valid model path.
4. Save settings.

<!-- ### Screenshot Placeholder: SAM3 Enabled In Settings

![SAM3 enabled settings placeholder](../../images/screenshots/sam3-settings-enabled.png) -->

## Runtime Behavior

When available and enabled:

- Image embeddings are prepared after image load.
- Candidate boxes may be generated from concept context.
- Candidate accept/reject controls appear above canvas.
- Hover point prompts can propose additional boxes.

<!-- ### Screenshot Placeholder: SAM Status Ready

![SAM status ready placeholder](../../images/screenshots/sam3-status-ready.png) -->

<!-- ### Screenshot Placeholder: SAM Candidate Controls Visible

![SAM candidate controls placeholder](../../images/screenshots/sam3-candidate-controls.png) -->

<!-- ### Screenshot Placeholder: Hover Prompt Candidate

![SAM hover candidate placeholder](../../images/screenshots/sam3-hover-candidate.png) -->

## Candidate Review Workflow

1. Select target observation.
2. Inspect generated candidate.
3. Accept if valid; reject if invalid.
4. Continue until no candidates remain.

<!-- ### Screenshot Placeholder: Candidate Accepted

![SAM candidate accepted placeholder](../../images/screenshots/sam3-candidate-accepted.png) -->

<!-- ### Screenshot Placeholder: Candidate Rejected

![SAM candidate rejected placeholder](../../images/screenshots/sam3-candidate-rejected.png) -->

## Common Failure Modes

- Model not found.
- Model incompatible or unavailable backend.
- Embedding still loading.

<!-- ### Screenshot Placeholder: SAM Unavailable State

![SAM unavailable placeholder](../../images/screenshots/sam3-unavailable-state.png) -->

<!-- ### Screenshot Placeholder: SAM Embedding Loading State

![SAM embedding loading placeholder](../../images/screenshots/sam3-embedding-loading.png) -->
