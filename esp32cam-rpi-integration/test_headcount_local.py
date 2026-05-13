from pathlib import Path
from headcount_manager import HeadcountManager

MODEL_PATH     = Path("best.pt")
OUTPUT_DIR     = Path("yolo_captures")
IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

if __name__ == "__main__":
    source = input("Enter folder path containing images: ").strip().strip('"')
    source_dir = Path(source)

    if not source_dir.exists() or not source_dir.is_dir():
        print(f"Invalid folder path: {source_dir}")
        exit()

    images = [f for f in source_dir.iterdir() if f.suffix.lower() in IMG_EXTENSIONS]
    if not images:
        print("No images found in that folder.")
        exit()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manager = HeadcountManager(
        esp32_url=None,
        model_path=MODEL_PATH,
        output_dir=OUTPUT_DIR,
        interval_s=30,
        resize=(640, 640),
        show_labels=False
    )

    print(f"\nFound {len(images)} image(s) in {source_dir}")
    print("=" * 55)

    for image_path in sorted(images):
        output_path = OUTPUT_DIR / image_path.name
        result = manager.process_image(image_path, output_path)
        manager._print_result(result)

    print("=" * 55)
    print(f"Done. Annotated images saved to: {OUTPUT_DIR.resolve()}")
