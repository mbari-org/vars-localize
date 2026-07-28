import pytest

from vars_localize.services.SAM3Service import SAM3Service


class _FakeModel:
    def __init__(self):
        self.set_classes_calls = []

    def set_classes(self, text):
        self.set_classes_calls.append(text)


class _FakeSemanticPredictor:
    def __init__(self, masks=None, boxes=None):
        self._masks = masks
        self._boxes = boxes
        self.prompts = {}
        self.reset_prompts_calls = 0
        self.inference_calls = []
        self.model = _FakeModel()

    def reset_prompts(self):
        self.reset_prompts_calls += 1
        self.prompts = {}

    def inference_features(
        self, features, src_shape, bboxes=None, labels=None, text=None
    ):
        self.inference_calls.append(
            {
                "features": features,
                "src_shape": src_shape,
                "bboxes": bboxes,
                "text": text,
            }
        )
        return self._masks, self._boxes


def _ready_service(masks=None, boxes=None):
    service = SAM3Service(model_path="/tmp/model.pt")
    predictor = _FakeSemanticPredictor(masks=masks, boxes=boxes)
    service._semantic_predictor = predictor
    service._semantic_features = {"feat": True}
    service._src_shape = (100, 100)
    return service, predictor


def test_query_boxes_returns_empty_without_calling_inference_when_no_boxes():
    service, predictor = _ready_service()

    assert service.query_boxes([]) == []
    assert predictor.inference_calls == []


def test_query_boxes_raises_when_semantic_unavailable():
    service = SAM3Service(model_path="/tmp/model.pt")

    with pytest.raises(RuntimeError):
        service.query_boxes([(0, 0, 10, 10)])


def test_query_boxes_returns_empty_when_features_not_ready():
    service = SAM3Service(model_path="/tmp/model.pt")
    service._semantic_predictor = _FakeSemanticPredictor()

    assert service.query_boxes([(0, 0, 10, 10)]) == []


def test_query_boxes_calls_inference_features_with_bboxes_and_no_text():
    service, predictor = _ready_service(boxes=[[0, 0, 10, 10, 0.9, 0]])

    service.query_boxes([(1, 2, 3, 4)])

    assert len(predictor.inference_calls) == 1
    call = predictor.inference_calls[0]
    assert call["bboxes"] == [(1, 2, 3, 4)]
    assert call["text"] is None
    assert call["src_shape"] == (100, 100)


def test_query_boxes_falls_back_to_normalize_boxes_when_no_masks():
    service, predictor = _ready_service(masks=None, boxes=[[0, 0, 10, 10, 0.9, 0]])

    result = service.query_boxes([(1, 2, 3, 4)])

    assert result == [(0, 0, 10, 10)]


def test_query_boxes_resets_prompt_state_around_inference():
    service, predictor = _ready_service(boxes=[])

    service.query_boxes([(1, 2, 3, 4)])

    assert predictor.reset_prompts_calls >= 2
    assert predictor.model.set_classes_calls == [["visual"]]
