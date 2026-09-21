"""
Camera motion estimator: affine/partial-affine with robust fitting, scene cut detection.
"""
import cv2
import numpy as np
from typing import List, Tuple, Dict
from .interfaces import FrameData, CameraMotion

class CameraMotionEstimator:
    def __init__(self, model: str = "affine", ransac_thresh: float = 3.0, min_inliers: float = 0.3):
        self.model = model
        self.ransac_thresh = ransac_thresh
        self.min_inliers = min_inliers

    def estimate(self, frames: List[FrameData]) -> CameraMotion:
        if not frames:
            return CameraMotion(transforms=[], segments=[], quality={"method": "none"})

        # Use first frame as reference for first segment
        transforms = []
        segments = []
        current_segment_start = 0

        # Identity for first frame
        identity = np.eye(3)
        transforms.append(identity)

        # For scene cut detection, track inlier ratio
        prev_gray = cv2.cvtColor(frames[0].image, cv2.COLOR_BGR2GRAY) if len(frames[0].image.shape)==3 else frames[0].image

        # Reference transform is from frame to reference (first frame of segment)
        # We'll accumulate: S_t maps canonical t to reference
        # For frame 0, S_0 = I
        # For frame t, estimate transform from frame t to frame t-1, then compose with S_{t-1}

        accumulated = identity

        for idx in range(1, len(frames)):
            curr = frames[idx]
            curr_gray = cv2.cvtColor(curr.image, cv2.COLOR_BGR2GRAY) if len(curr.image.shape)==3 else curr.image

            # Detect features and track
            # Use ORB or goodFeaturesToTrack + optical flow
            prev_pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=30, blockSize=3)
            if prev_pts is None or len(prev_pts) < 4:
                # Not enough features, assume identity and possible scene cut?
                transforms.append(accumulated.copy())
                prev_gray = curr_gray
                continue

            curr_pts, status, err = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, prev_pts, None)
            if curr_pts is None:
                transforms.append(accumulated.copy())
                prev_gray = curr_gray
                continue

            # Filter valid
            good_prev = prev_pts[status==1]
            good_curr = curr_pts[status==1]

            if len(good_prev) < 4:
                transforms.append(accumulated.copy())
                prev_gray = curr_gray
                continue

            # Estimate affine partial
            # Use RANSAC
            if self.model == "affine":
                M, inliers = cv2.estimateAffine2D(good_prev, good_curr, method=cv2.RANSAC, ransacReprojThreshold=self.ransac_thresh)
            else:  # partial affine
                M, inliers = cv2.estimateAffinePartial2D(good_prev, good_curr, method=cv2.RANSAC, ransacReprojThreshold=self.ransac_thresh)

            if M is None:
                # Scene cut?
                inlier_ratio = 0
                M = np.eye(2,3)
            else:
                inlier_ratio = np.sum(inliers) / len(inliers) if inliers is not None else 0

            # Check scene cut
            if inlier_ratio < self.min_inliers:
                # New segment
                segments.append((current_segment_start, idx-1))
                current_segment_start = idx
                accumulated = identity
                transforms.append(identity)
                prev_gray = curr_gray
                continue

            # Convert 2x3 to 3x3
            M_3x3 = np.eye(3)
            M_3x3[0:2, :] = M

            # Check plausibility
            from ..core.geometry import is_transform_plausible
            # M is from prev to curr, but we need S_t which maps curr to reference
            # We have accumulated = S_{t-1} (maps prev to ref)
            # To get S_t: we need transform from curr to prev, then to ref: S_t = S_{t-1} * (transform curr->prev)
            # Our M is prev->curr, so invert it to get curr->prev
            try:
                M_inv = np.linalg.inv(M_3x3)
            except np.linalg.LinAlgError:
                M_inv = np.eye(3)

            # Compose
            new_accumulated = accumulated @ M_inv

            # Plausibility check on M_inv
            if not is_transform_plausible(M_inv, curr.canonical_width, curr.canonical_height):
                # Reject, keep previous accumulated
                transforms.append(accumulated.copy())
            else:
                accumulated = new_accumulated
                transforms.append(accumulated.copy())

            prev_gray = curr_gray

        # Close last segment
        segments.append((current_segment_start, len(frames)-1))

        quality = {
            "method": self.model,
            "segments": len(segments),
            "frames": len(frames)
        }

        return CameraMotion(transforms=transforms, segments=segments, quality=quality)
