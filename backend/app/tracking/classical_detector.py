"""
Classical candidate detector for golf ball.
Uses image evidence, local contrast, motion cues, bounded local search.
"""
import cv2
import numpy as np
from typing import List, Optional, Tuple
from .interfaces import Candidate, FrameData

class ClassicalDetector:
    def __init__(self, min_radius: int = 2, max_radius: int = 20, contrast_thresh: float = 15.0):
        self.min_radius = min_radius
        self.max_radius = max_radius
        self.contrast_thresh = contrast_thresh

    def detect(self, frame: FrameData, roi: Optional[Tuple[float,float,float,float]] = None, camera_transform: Optional[np.ndarray] = None) -> List[Candidate]:
        img = frame.image
        h, w = img.shape[:2]
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape)==3 else img

        # ROI in normalized coords? roi = (x_min, y_min, x_max, y_max) normalized
        x0, y0, x1, y1 = 0,0,w,h
        if roi:
            nx0, ny0, nx1, ny1 = roi
            x0 = int(nx0 * w)
            y0 = int(ny0 * h)
            x1 = int(nx1 * w)
            y1 = int(ny1 * h)
            x0 = max(0, min(w, x0))
            y0 = max(0, min(h, y0))
            x1 = max(0, min(w, x1))
            y1 = max(0, min(h, y1))

        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            return []

        # Local contrast: white top-hat for bright small objects on darker background
        # Also use LoG
        kernel_size = self.max_radius*2+1
        # Top-hat
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        tophat = cv2.morphologyEx(crop, cv2.MORPH_TOPHAT, kernel)

        # Threshold
        _, thresh = cv2.threshold(tophat, self.contrast_thresh, 255, cv2.THRESH_BINARY)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Filter by area corresponding to radius
            min_area = np.pi * (self.min_radius**2) * 0.5
            max_area = np.pi * (self.max_radius**2) * 2.0
            if area < min_area or area > max_area:
                continue
            # Circularity
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter*perimeter)
            if circularity < 0.4:
                continue
            # Bounding rect aspect
            x,y,wc,hc = cv2.boundingRect(cnt)
            aspect = wc / hc if hc!=0 else 0
            if aspect < 0.5 or aspect > 2.0:
                continue

            # Centroid
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"]/M["m00"])
            cy = int(M["m01"]/M["m00"])

            # Score: mean tophat value + circularity
            mask = np.zeros(crop.shape, dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            mean_val = cv2.mean(tophat, mask=mask)[0]
            score = (mean_val / 255.0) * 0.7 + circularity * 0.3

            # Convert to normalized coords in canonical frame
            # cx,cy in crop coords, add offset
            abs_x = x0 + cx
            abs_y = y0 + cy
            # Image is already canonical? Assume FrameData image is canonical
            x_norm = abs_x / frame.canonical_width if frame.canonical_width else abs_x / w
            y_norm = abs_y / frame.canonical_height if frame.canonical_height else abs_y / h

            radius = np.sqrt(area / np.pi)

            candidates.append(Candidate(
                frame_index=frame.frame_index,
                x_norm=float(x_norm),
                y_norm=float(y_norm),
                score=float(score),
                radius=float(radius),
                provenance="detected"
            ))

        # Sort by score descending, keep top 10
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:10]
