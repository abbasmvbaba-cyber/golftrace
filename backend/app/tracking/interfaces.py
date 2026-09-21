from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Tuple
import numpy as np

class Candidate:
    def __init__(self, frame_index: int, x_norm: float, y_norm: float, score: float, radius: float, provenance: str = "detected"):
        self.frame_index = frame_index
        self.x_norm = x_norm
        self.y_norm = y_norm
        self.score = score
        self.radius = radius
        self.provenance = provenance

class FrameData:
    def __init__(self, frame_index: int, pts_us: int, image: np.ndarray, canonical_width: int, canonical_height: int):
        self.frame_index = frame_index
        self.pts_us = pts_us
        self.image = image
        self.canonical_width = canonical_width
        self.canonical_height = canonical_height

class CameraMotion:
    def __init__(self, transforms: List[np.ndarray], segments: List[Tuple[int,int]], quality: Dict):
        self.transforms = transforms  # S_t list
        self.segments = segments
        self.quality = quality

class TrackPoint:
    def __init__(self, frame_index: int, pts_us: int, x_norm: Optional[float], y_norm: Optional[float],
                 provenance: str, visibility: str, score: Optional[float]=None, is_anchor: bool=False):
        self.frame_index = frame_index
        self.pts_us = pts_us
        self.x_norm = x_norm
        self.y_norm = y_norm
        self.provenance = provenance  # detected/manual/predicted/interpolated/artistic
        self.visibility = visibility  # visible/not_visible/out_of_frame
        self.score = score
        self.is_anchor = is_anchor

    def to_dict(self):
        return {
            "frame_index": self.frame_index,
            "pts_us": self.pts_us,
            "x_norm": self.x_norm,
            "y_norm": self.y_norm,
            "provenance": self.provenance,
            "visibility": self.visibility,
            "score": self.score,
            "is_anchor": self.is_anchor
        }

class FrameSourceInterface(ABC):
    @abstractmethod
    def get_frame(self, frame_index: int) -> FrameData:
        pass

class CandidateDetectorInterface(ABC):
    @abstractmethod
    def detect(self, frame: FrameData, roi: Optional[Tuple[float,float,float,float]], camera_transform: Optional[np.ndarray]) -> List[Candidate]:
        pass

class CameraMotionEstimatorInterface(ABC):
    @abstractmethod
    def estimate(self, frames: List[FrameData]) -> CameraMotion:
        pass

class TemporalTrackerInterface(ABC):
    @abstractmethod
    def track(self, frames: List[FrameData], candidates: Dict[int, List[Candidate]], anchors: Dict[int, TrackPoint], camera_motion: CameraMotion, config: Dict) -> List[TrackPoint]:
        pass

class GapPolicyInterface(ABC):
    @abstractmethod
    def apply(self, track: List[TrackPoint], max_gap_ms: int) -> List[TrackPoint]:
        pass

class DisplayPathGeneratorInterface(ABC):
    @abstractmethod
    def generate(self, track: List[TrackPoint], camera_motion: CameraMotion, config: Dict) -> List[TrackPoint]:
        pass

class ModelAdapterInterface(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def detect(self, frame: FrameData) -> List[Candidate]:
        pass

    @abstractmethod
    def get_info(self) -> Dict:
        pass
