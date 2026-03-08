"""FastAPI inference API with GPU support."""

from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model once at startup."""
    global model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # Replace with your model loading logic
    model = {"device": device, "loaded": True}
    print(f"Model loaded on {device}")
    yield
    model = None


app = FastAPI(title="Inference API", lifespan=lifespan)


@app.get("/health")
async def health():
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "gpu": gpu_name,
        "cuda": torch.version.cuda if gpu_available else None,
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)):  # noqa: B008
    """Run inference on uploaded image. Replace with your model logic."""
    if model is None:
        return JSONResponse(status_code=503, content={"error": "Model not loaded"})

    contents = await file.read()
    # Replace this with actual inference:
    # image = Image.open(io.BytesIO(contents))
    # result = model(image)

    return {
        "filename": file.filename,
        "size_bytes": len(contents),
        "device": model["device"],
        "prediction": "Replace with actual model output",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
