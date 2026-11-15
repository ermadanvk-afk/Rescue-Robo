import argparse
import random
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare and validate YOLO dataset")
    parser.add_argument("--src-images", type=str, default="",
                        help="Path to folder containing raw training images")
    parser.add_argument("--src-labels", type=str, default="",
                        help="Path to folder containing raw YOLO txt label files")
    parser.add_argument("--output-dir", type=str, default=str(DATASET_DIR),
                        help="Target dataset directory")
    parser.add_argument("--split", type=float, default=0.8,
                        help="Train split ratio (default: 0.8 = 80%% train, 20%% val)")
    parser.add_argument("--classes", type=str, default="person",
                        help="Comma-separated class names (e.g. 'person,survivor,fire_hazard')")
    parser.add_argument("--verify", action="store_true",
                        help="Verify dataset structure and label validity")
    return parser.parse_args()


def verify_dataset(dataset_path):
    dataset_path = Path(dataset_path)
    print(f"[Verify] Checking dataset structure in {dataset_path}...")

    train_imgs = list((dataset_path / "images" / "train").glob("*.*"))
    val_imgs = list((dataset_path / "images" / "val").glob("*.*"))
    train_lbls = list((dataset_path / "labels" / "train").glob("*.txt"))
    val_lbls = list((dataset_path / "labels" / "val").glob("*.txt"))
    yaml_file = dataset_path / "data.yaml"

    print(f"  Train images: {len(train_imgs)} | Train labels: {len(train_lbls)}")
    print(f"  Val images  : {len(val_imgs)} | Val labels  : {len(val_lbls)}")
    print(f"  data.yaml   : {'EXISTS' if yaml_file.exists() else 'MISSING'}")

    # Check for empty labels or coordinate anomalies
    corrupt_labels = 0
    for lbl in train_lbls + val_lbls:
        with open(lbl, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 5:
                    corrupt_labels += 1
                    break
                try:
                    cls_id = int(parts[0])
                    x, y, w, h = map(float, parts[1:])
                    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0):
                        corrupt_labels += 1
                        break
                except ValueError:
                    corrupt_labels += 1
                    break

    if corrupt_labels > 0:
        print(f"  [Warning] Found {corrupt_labels} label files with format or coordinate issues.")
    else:
        print("  [Success] All labels adhere to standard YOLO normalized [0, 1] format.")


def main():
    args = parse_args()
    out_dir = Path(args.output_dir)

    if args.verify:
        verify_dataset(out_dir)
        return

    # Create destination directories
    img_train = out_dir / "images" / "train"
    img_val = out_dir / "images" / "val"
    lbl_train = out_dir / "labels" / "train"
    lbl_val = out_dir / "labels" / "val"

    for d in [img_train, img_val, lbl_train, lbl_val]:
        d.mkdir(parents=True, exist_ok=True)

    class_names = [c.strip() for c in args.classes.split(",") if c.strip()]

    # Generate data.yaml
    yaml_content = f"""# AI Rescue Robot Dataset Configuration
path: {out_dir.resolve().as_posix()}
train: images/train
val: images/val

# Classes
names:
"""
    for idx, name in enumerate(class_names):
        yaml_content += f"  {idx}: {name}\n"

    yaml_path = out_dir / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print(f"[Dataset] Generated YAML configuration at: {yaml_path}")

    # If raw source provided, split images and labels
    if args.src_images:
        src_img_dir = Path(args.src_images)
        src_lbl_dir = Path(args.src_labels) if args.src_labels else src_img_dir
        valid_exts = (".jpg", ".jpeg", ".png", ".bmp")
        images = [f for f in src_img_dir.iterdir() if f.suffix.lower() in valid_exts]

        random.seed(42)
        random.shuffle(images)

        split_idx = int(len(images) * args.split)
        train_set = images[:split_idx]
        val_set = images[split_idx:]

        for img in train_set:
            shutil.copy(img, img_train / img.name)
            lbl = src_lbl_dir / f"{img.stem}.txt"
            if lbl.exists():
                shutil.copy(lbl, lbl_train / lbl.name)

        for img in val_set:
            shutil.copy(img, img_val / img.name)
            lbl = src_lbl_dir / f"{img.stem}.txt"
            if lbl.exists():
                shutil.copy(lbl, lbl_val / lbl.name)

        print(f"[Dataset] Split {len(images)} images -> {len(train_set)} train, {len(val_set)} val.")

    verify_dataset(out_dir)


if __name__ == "__main__":
    main()
