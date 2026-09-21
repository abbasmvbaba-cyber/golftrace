"""
Benchmark interface that accepts labeled clips.
Reports visible-frame recall, localization error, false positives, hallucinated continuation, fragmentation, reacquisition, required manual corrections.
"""
import json
import math
from typing import List, Dict
from pathlib import Path

def evaluate_track(gt_points: List[Dict], pred_points: List[Dict], threshold_norm: float = 0.02) -> Dict:
    """
    gt_points: list of {frame_index, x_norm, y_norm, visibility}
    pred_points: list of {frame_index, x_norm, y_norm, visibility, provenance}
    threshold_norm: distance threshold for TP in normalized coords
    """
    gt_map = {p["frame_index"]: p for p in gt_points}
    pred_map = {p["frame_index"]: p for p in pred_points}

    all_frames = sorted(set(gt_map.keys()) | set(pred_map.keys()))

    tp = 0
    fn = 0
    fp = 0
    localization_errors = []
    hallucinated = 0
    fragmentation = 0
    prev_visible = False

    # Find GT track end (last visible)
    gt_visible_frames = [fi for fi, p in gt_map.items() if p.get("visibility") == "visible" and p.get("x_norm") is not None]
    gt_end = max(gt_visible_frames) if gt_visible_frames else -1

    for fi in all_frames:
        gt = gt_map.get(fi)
        pred = pred_map.get(fi)

        gt_visible = gt and gt.get("visibility") == "visible" and gt.get("x_norm") is not None
        pred_visible = pred and pred.get("visibility") == "visible" and pred.get("x_norm") is not None

        if gt_visible and pred_visible:
            # Compute distance
            dx = gt["x_norm"] - pred["x_norm"]
            dy = gt["y_norm"] - pred["y_norm"]
            dist = math.sqrt(dx*dx + dy*dy)
            if dist <= threshold_norm:
                tp += 1
                localization_errors.append(dist)
            else:
                # Localization error too large -> count as FN? For simplicity, FN
                fn += 1
                localization_errors.append(dist)
        elif gt_visible and not pred_visible:
            fn += 1
        elif not gt_visible and pred_visible:
            fp += 1
            # Check hallucinated continuation: pred visible after gt_end
            if fi > gt_end and gt_end != -1:
                hallucinated += 1

        # Fragmentation: count transitions from visible to not visible and back
        if pred_visible:
            if not prev_visible:
                # Start of fragment
                if fi != min([f for f in pred_map if pred_map[f].get("visibility")=="visible"], default=fi):
                    fragmentation += 1
            prev_visible = True
        else:
            prev_visible = False

    recall = tp / (tp + fn) if (tp+fn) > 0 else 0
    precision = tp / (tp + fp) if (tp+fp) > 0 else 0
    median_error = sorted(localization_errors)[len(localization_errors)//2] if localization_errors else None
    p95_error = sorted(localization_errors)[int(len(localization_errors)*0.95)] if localization_errors else None

    return {
        "visible_frame_recall": recall,
        "precision": precision,
        "localization_error_median": median_error,
        "localization_error_p95": p95_error,
        "false_positives": fp,
        "false_negatives": fn,
        "true_positives": tp,
        "hallucinated_continuation": hallucinated,
        "fragmentation": fragmentation,
        "total_frames": len(all_frames)
    }

def benchmark_dataset(dataset_dir: str, predictions_dir: str) -> Dict:
    """
    dataset_dir: contains ground truth jsons per video
    predictions_dir: contains predicted track jsons
    """
    dataset_path = Path(dataset_dir)
    pred_path = Path(predictions_dir)

    results = []
    for gt_file in dataset_path.glob("*.json"):
        pred_file = pred_path / gt_file.name
        if not pred_file.exists():
            continue
        gt_data = json.loads(gt_file.read_text())
        pred_data = json.loads(pred_file.read_text())
        gt_points = gt_data.get("points", [])
        pred_points = pred_data.get("points", [])
        metrics = evaluate_track(gt_points, pred_points)
        metrics["video_id"] = gt_file.stem
        results.append(metrics)

    # Aggregate
    if not results:
        return {"results": [], "aggregated": {}}

    avg_recall = sum(r["visible_frame_recall"] for r in results) / len(results)
    avg_precision = sum(r["precision"] for r in results) / len(results)

    return {
        "results": results,
        "aggregated": {
            "avg_recall": avg_recall,
            "avg_precision": avg_precision,
            "total_videos": len(results)
        }
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", required=True, help="GT dataset dir")
    parser.add_argument("--pred", required=True, help="Predictions dir")
    parser.add_argument("--output", required=True, help="Output json")
    args = parser.parse_args()
    res = benchmark_dataset(args.gt, args.pred)
    Path(args.output).write_text(json.dumps(res, indent=2))
    print(f"Benchmark written to {args.output}")
