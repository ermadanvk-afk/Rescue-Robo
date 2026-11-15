import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"


def parse_args():
    parser = argparse.ArgumentParser(description="Export YOLO model to edge formats (ONNX, TFLite, NCNN)")
    parser.add_argument("--model", type=str, default=str(MODEL_DIR / "yolo11n.pt"),
                        help="Path to YOLO .pt model weights")
    parser.add_argument("--format", type=str, default="onnx",
                        choices=["onnx", "tflite", "ncnn", "openvino", "engine"],
                        help="Export format (onnx is recommended for Raspberry Pi 5 CPU)")
    parser.add_argument("--imgsz", type=int, default=480,
                        help="Inference image resolution (480 or 640)")
    parser.add_argument("--half", action="store_true",
                        help="Use FP16 half-precision")
    return parser.parse_args()


def main():
    args = parse_args()
    model_path = Path(args.model)

    print("==================================================")
    print("      AI RESCUE ROBOT - MODEL EXPORT UTILITY      ")
    print("==================================================")
    print(f"Input Model : {model_path}")
    print(f"Target Format: {args.format.upper()}")
    print(f"Image Size  : {args.imgsz}")
    print("==================================================\n")

    if not model_path.exists():
        # Check if model name can be resolved automatically
        candidate = MODEL_DIR / model_path.name
        if candidate.exists():
            model_path = candidate
        else:
            print(f"[ERROR] Model file {args.model} not found.")
            print("Run 'python training/download_weights.py' first.")
            sys.exit(1)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] 'ultralytics' library is not installed.")
        print("Install it with: pip install ultralytics")
        sys.exit(1)

    print(f"[Export] Loading model from {model_path}...")
    model = YOLO(str(model_path))

    print(f"[Export] Converting to {args.format.upper()}...")
    try:
        exported_path = model.export(
            format=args.format,
            imgsz=args.imgsz,
            half=args.half,
            dynamic=False
        )
        print(f"\n[Success] Model successfully exported to: {exported_path}")
        print(f"Copy this model file to your Raspberry Pi for high-FPS edge inference.")
    except Exception as exc:
        print(f"\n[Export Failed] Error during conversion: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
