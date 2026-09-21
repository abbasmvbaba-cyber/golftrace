"""
Model adapter interface for small-object center detector / heatmap model.
No pretrained weight is assumed to exist. This is a configurable adapter.

To be implemented after manual and classical vertical slices work.

Expected to preserve source detail using crops or tiles.
Support model version, checksum, preprocessing config, license metadata.
"""

from typing import List, Dict, Optional
from .interfaces import Candidate, FrameData, ModelAdapterInterface
import os

class ModelAdapter(ModelAdapterInterface):
    """
    Configurable adapter for a small-object detector.
    Currently reports not available unless model weights configured.
    """

    def __init__(self, model_path: Optional[str] = None, config: Optional[Dict] = None):
        self.model_path = model_path
        self.config = config or {}
        self.model = None
        self._load_model()

    def _load_model(self):
        # Check if model path exists and is valid
        if not self.model_path:
            return
        if not os.path.exists(self.model_path):
            print(f"Model path {self.model_path} does not exist")
            return
        # TODO: Load actual model (e.g., PyTorch)
        # For now, placeholder
        # Example:
        # import torch
        # self.model = torch.load(self.model_path)
        # self.model.eval()
        print(f"Model loading not implemented, path {self.model_path}")

    def is_available(self) -> bool:
        return self.model is not None

    def detect(self, frame: FrameData) -> List[Candidate]:
        if not self.is_available():
            raise RuntimeError("Model not available, use classical or manual workflow")
        # TODO: Implement detection with tiling to preserve detail
        # Steps:
        # 1. Split frame into tiles (e.g., 640x640) with overlap
        # 2. Run model on each tile
        # 3. Merge candidates via NMS
        # 4. Convert to normalized coords
        return []

    def get_info(self) -> Dict:
        return {
            "model_path": self.model_path,
            "config": self.config,
            "available": self.is_available(),
            "license": self.config.get("license", "unknown"),
            "version": self.config.get("version", "0.0.0"),
            "checksum": self.config.get("checksum", None),
            "preprocessing": self.config.get("preprocessing", {}),
            "note": "No pretrained weight assumed to exist. This adapter requires external weights and license verification."
        }

# Factory
def create_model_adapter() -> ModelAdapterInterface:
    from ..config import settings
    # Check env for model path
    model_path = os.getenv("MODEL_PATH")
    model_config = {
        "license": os.getenv("MODEL_LICENSE", "unknown"),
        "version": os.getenv("MODEL_VERSION", "0.0.0"),
        "checksum": os.getenv("MODEL_CHECKSUM"),
        "preprocessing": {
            "tile_size": 640,
            "overlap": 0.2,
            "long_edge": 1920
        }
    }
    return ModelAdapter(model_path=model_path, config=model_config)
