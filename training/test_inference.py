import argparse
import time
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"


def parse_args():
    parser = argparse.ArgumentParser(description="Test YOLO model inference on image or camera")
    parser.add_argument("--model", type=str, default=str(MODEL_DIR / "yolo11n.pt"),
                        help="Path to .pt or .onnx model weights")
    parser.add_argument("--source", type=str, default="0",
                        help="Input source: '0' for webcam, or path to an image/video file")
    parser.add_argument("--conf", type=float, default=0.35,
                        help="Confidence threshold")
    parser.add_argument("--save-dir", type=str, default=str(BASE_DIR / "recordings" / "test_output"),
                        help="Directory to save annotated test outputs")
    return parser.parse_args()


def main():
    args = parse_args()
    save_path = Path(args.save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] 'ultralytics' library is not installed.")
        sys.exit(1)

    model_path = Path(args.model)
    if not model_path.exists():
        candidate = MODEL_DIR / model_path.name
        if candidate.exists():
            model_path = candidate
        else:
            print(f"[Warning] Model file {args.model} not found locally; Ultralytics will attempt auto-download.")
            model_path = args.model

    print(f"[Inference] Loading model: {model_path}")
    model = YOLO(str(model_path))

    # Determine if source is camera index or file
    source = int(args.source) if args.source.isdigit() else args.source

    print(f"[Inference] Running prediction on source: {source} (conf={args.conf})...")
    t0 = time.time()
    results = model.predict(source=source, conf=args.conf, save=True, project=str(save_path), name="predict", exist_ok=True)
    dt = time.time() - t0

    print(f"\n[Done] Processed in {dt:.3f} seconds.")
    for r in results:
        boxes = r.boxes
        if boxes is not None:
            print(f"  Detections found: {len(boxes)}")
            for b in boxes:
                cls_id = int(b.cls[0])
                cls_name = r.names.get(cls_id, str(cls_id))
                conf = float(b.conf[0])
                print(f"    - {cls_name}: {conf:.2f}")

    print(f"Annotated output saved in: {save_path / 'predict'}")


if __name__ == "__main__":
    main()
