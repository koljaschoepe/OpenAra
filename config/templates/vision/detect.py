"""Object detection demo with YOLO11 — image and webcam modes."""

import sys
from pathlib import Path

from ultralytics import YOLO


def detect_image(image_path: str, model_name: str = "yolo11n.pt"):
    """Run detection on a single image."""
    model = YOLO(model_name)
    results = model(image_path)

    for r in results:
        boxes = r.boxes
        print(f"Detected {len(boxes)} objects in {image_path}")
        for box in boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            label = model.names[cls]
            print(f"  {label}: {conf:.1%}")

    # Save annotated image
    out_path = Path(image_path).stem + "_detected.jpg"
    results[0].save(out_path)
    print(f"Saved: {out_path}")


def detect_webcam(model_name: str = "yolo11n.pt", source: int = 0):
    """Run real-time detection on webcam feed."""
    model = YOLO(model_name)
    results = model(source=source, stream=True, show=False)

    for r in results:
        boxes = r.boxes
        if len(boxes) > 0:
            labels = [f"{model.names[int(b.cls[0])]} ({float(b.conf[0]):.0%})" for b in boxes]
            print(f"Frame: {', '.join(labels)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--webcam":
        detect_webcam()
    elif len(sys.argv) > 1:
        detect_image(sys.argv[1])
    else:
        print("Usage:")
        print("  python detect.py image.jpg    # Detect in image")
        print("  python detect.py --webcam     # Real-time webcam")
