"""Typed models for imaged moment and observation tree entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from PyQt6.QtGui import QPixmap

from vars_localize.util.utils import extract_bounding_boxes

if TYPE_CHECKING:
    from vars_localize.ui.BoundingBox import SourceBoundingBox


@dataclass
class AssociationEntry:
    uuid: str
    link_name: str
    to_concept: Optional[str]
    link_value: str
    mime_type: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssociationEntry":
        return cls(
            uuid=str(data.get("uuid", "")),
            link_name=str(data.get("link_name", "")),
            to_concept=data.get("to_concept"),
            link_value=str(data.get("link_value", "")),
            mime_type=data.get("mime_type"),
            raw=dict(data),
        )

    def to_dict(self) -> Dict[str, Any]:
        return (
            dict(self.raw)
            if self.raw
            else {
                "uuid": self.uuid,
                "link_name": self.link_name,
                "to_concept": self.to_concept,
                "link_value": self.link_value,
                "mime_type": self.mime_type,
            }
        )


@dataclass
class ObservationEntry:
    uuid: str
    concept: str
    observer: str
    associations: List[AssociationEntry] = field(default_factory=list)
    boxes: List[SourceBoundingBox] = field(default_factory=list)
    video_boxes: List[SourceBoundingBox] = field(default_factory=list)
    status: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)
    box_manager: Any = None

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], image_reference_uuid: Optional[str]
    ) -> "ObservationEntry":
        uuid = str(data.get("uuid", ""))
        concept = str(data.get("concept", ""))
        associations = [
            AssociationEntry.from_dict(assoc)
            for assoc in data.get("associations", [])
            if isinstance(assoc, dict)
        ]
        source_boxes = list(
            extract_bounding_boxes(
                [assoc.to_dict() for assoc in associations],
                concept,
                uuid,
            )
        )
        boxes = [
            box
            for box in source_boxes
            if box.image_reference_uuid == image_reference_uuid
        ]
        video_boxes = [box for box in source_boxes if box.image_reference_uuid is None]

        return cls(
            uuid=uuid,
            concept=concept,
            observer=str(data.get("observer", "")),
            associations=associations,
            boxes=boxes,
            video_boxes=video_boxes,
            status=len(boxes),
            raw=dict(data),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.raw)
        data["uuid"] = self.uuid
        data["concept"] = self.concept
        data["observer"] = self.observer
        data["associations"] = [assoc.to_dict() for assoc in self.associations]
        return data


@dataclass
class ImagedMomentEntry:
    uuid: str
    observations: List[ObservationEntry]
    image_reference_uuid: Optional[str]
    image_url: Optional[str]
    video_reference_uuid: Optional[str]
    recorded_timestamp: Optional[str] = None
    timecode: Optional[str] = None
    elapsed_time_millis: Optional[int] = None
    ancillary_data: Dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)
    cached_image: Optional[QPixmap] = None
    video_data: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImagedMomentEntry":
        uuid = str(data.get("uuid", ""))

        image_references = [
            ref for ref in data.get("image_references", []) if isinstance(ref, dict)
        ]
        png_image_references = [
            ref for ref in image_references if ref.get("format") == "image/png"
        ]
        jpeg_image_references = [
            ref for ref in image_references if ref.get("format") == "image/jpeg"
        ]
        valid_image_references = png_image_references + jpeg_image_references

        image_reference_uuid = None
        image_url = None
        if valid_image_references:
            image_reference_uuid = valid_image_references[0].get("uuid")
            image_url = valid_image_references[0].get("url")

        observations = [
            ObservationEntry.from_dict(obs, image_reference_uuid)
            for obs in data.get("observations", [])
            if isinstance(obs, dict)
        ]

        elapsed_millis = data.get("elapsed_time_millis")
        try:
            elapsed_millis = int(elapsed_millis) if elapsed_millis is not None else None
        except (TypeError, ValueError):
            elapsed_millis = None

        return cls(
            uuid=uuid,
            observations=observations,
            image_reference_uuid=image_reference_uuid,
            image_url=image_url,
            video_reference_uuid=data.get("video_reference_uuid"),
            recorded_timestamp=data.get("recorded_timestamp"),
            timecode=data.get("timecode"),
            elapsed_time_millis=elapsed_millis,
            ancillary_data=data.get("ancillary_data") or {},
            raw=dict(data),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.raw)
        data["uuid"] = self.uuid
        data["video_reference_uuid"] = self.video_reference_uuid
        data["recorded_timestamp"] = self.recorded_timestamp
        data["timecode"] = self.timecode
        data["elapsed_time_millis"] = self.elapsed_time_millis
        data["ancillary_data"] = dict(self.ancillary_data)
        data["observations"] = [obs.to_dict() for obs in self.observations]
        return data


@dataclass
class PlaceholderEntry:
    label: str = "No results found."


EntryPayload = Union[ImagedMomentEntry, ObservationEntry, PlaceholderEntry]
