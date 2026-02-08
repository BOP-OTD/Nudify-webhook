from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime

app = FastAPI()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.get("/")
def root():
    return {
        "ok": True,
        "message": "Webhook server running",
        "webhook_endpoint": "/undress-photo-webhook",
        "expects_form_fields": ["id_gen", "image"]
    }

# Use THIS endpoint for undress (rename if you want)
@app.post("/undress-photo-webhook")
async def undress_photo_webhook(
    id_gen: str = Form(...),
    image: UploadFile = File(...),
    webhook: str = Form(None)  # optional, provider sends it but we don't need it
):
    # Make a clean filename
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = Path(image.filename).suffix or ".jpg"
    filename = f"undress_{id_gen}_{ts}{suffix}"
    outpath = UPLOAD_DIR / filename

    # Save the uploaded file bytes
    content = await image.read()
    outpath.write_bytes(content)

    print(f"✅ Saved: {outpath}")

    return JSONResponse({
        "ok": True,
        "saved_file": str(outpath),
        "id_gen": id_gen,
        "content_type": image.content_type
    })
