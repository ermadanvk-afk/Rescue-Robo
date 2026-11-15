import urllib.request
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Direct URLs to pre-trained nano models
WEIGHTS_URLS = {
    # Lightweight ONNX model: Runs on Raspberry Pi via OpenCV DNN with ZERO PyTorch dependency!
    "yolov8n.onnx": "https://huggingface.co/unileon-robotics/YOLO8-ONNX/resolve/main/yolov8n.onnx",
    # PyTorch checkpoints for fine-tuning on PC/Colab
    "yolo11n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    "yolov8n.pt": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
}


def download_file(url, dest_path):
    print(f"Downloading {dest_path.name} from {url}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            block_size = 65536

            with open(dest_path, "wb") as f:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = min(100.0, downloaded * 100.0 / total_size)
                        sys.stdout.write(f"\r  Progress: {percent:.1f}% ({downloaded / (1024*1024):.2f} MB)")
                        sys.stdout.flush()

        print("\nDownload complete!")
        return True
    except Exception as exc:
        print(f"\nDownload failed: {exc}")
        return False


def main():
    print("=" * 60)
    print("   AI RESCUE ROBOT - PRE-TRAINED WEIGHTS DOWNLOADER       ")
    print("=" * 60)

    for filename, url in WEIGHTS_URLS.items():
        target = MODEL_DIR / filename
        if target.exists() and target.stat().st_size > 1000000:
            print(f"[{filename}] Already exists at: {target} ({target.stat().st_size / (1024*1024):.2f} MB)")
        else:
            download_file(url, target)

    print("\nAll weights ready in models/ folder.")


if __name__ == "__main__":
    main()
