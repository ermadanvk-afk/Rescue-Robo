import argparse
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Train / Fine-tune YOLO model for Rescue Robot")
    parser.add_argument("--data", type=str, default="coco8.yaml",
                        help="Path to dataset YAML file (e.g. dataset/data.yaml or coco8.yaml for test)")
    parser.add_argument("--model", type=str, default="yolo11n.pt",
                        help="Base pre-trained model weights (e.g. yolo11n.pt, yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="Image resolution for training (e.g. 640, 480, 320)")
    parser.add_argument("--batch", type=int, default=16,
                        help="Batch size (reduce to 8 or 4 if GPU runs out of VRAM)")
    parser.add_argument("--device", type=str, default="",
                        help="Device to run on: '0' for CUDA GPU, 'cpu' for CPU, or '' for auto-detection")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of dataloader worker threads")
    parser.add_argument("--output", type=str, default=str(MODEL_DIR / "best.pt"),
                        help="Path to save the resulting fine-tuned weights")
    parser.add_argument("--export-onnx", action="store_true", default=True,
                        help="Automatically export to ONNX format after training for fast Pi inference")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check setup and configuration without executing long training")
    return parser.parse_args()


def main():
    args = parse_args()

    print("==================================================")
    print("      AI RESCUE ROBOT - MODEL TRAINING PIPELINE   ")
    print("==================================================")
    print(f"Base Model    : {args.model}")
    print(f"Dataset Config: {args.data}")
    print(f"Epochs        : {args.epochs}")
    print(f"Image Size    : {args.imgsz}")
    print(f"Batch Size    : {args.batch}")
    print(f"Target Output : {args.output}")
    print("==================================================\n")

    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] 'ultralytics' library is not installed.")
        print("Install it with: pip install ultralytics")
        print("Note: Train on a machine with an NVIDIA GPU or Google Colab for best results.")
        sys.exit(1)

    if args.dry_run:
        print("[DRY-RUN] Verified dependencies and arguments successfully.")
        return

    # Check if local model weights exist in models/
    local_weights = MODEL_DIR / args.model
    model_source = str(local_weights) if local_weights.exists() else args.model

    print(f"[Training] Loading base model from: {model_source}")
    model = YOLO(model_source)

    # Device configuration
    device_arg = args.device if args.device else None

    print(f"[Training] Starting training on {args.data} for {args.epochs} epochs...")
    train_results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device_arg,
        workers=args.workers,
        project=str(BASE_DIR / "runs" / "train"),
        name="rescue_model",
        exist_ok=True
    )

    # Locate and copy best weights
    best_weights = Path(model.trainer.save_dir) / "weights" / "best.pt"
    if best_weights.exists():
        dest = Path(args.output)
        shutil.copy(str(best_weights), str(dest))
        print(f"\n[Success] Best fine-tuned weights saved to: {dest}")

        # Optional ONNX Export for Raspberry Pi deployment
        if args.export_onnx:
            print("\n[Export] Exporting best model to ONNX for Raspberry Pi...")
            trained_model = YOLO(str(dest))
            onnx_path = trained_model.export(format="onnx", imgsz=args.imgsz, dynamic=False)
            print(f"[Export] ONNX model ready at: {onnx_path}")
    else:
        print("\n[Warning] Training completed but best.pt could not be located in trainer save dir.")


if __name__ == "__main__":
    main()
