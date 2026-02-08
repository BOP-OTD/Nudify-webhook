from fastapi import FastAPI, UploadFile, File, Form, Request
from pathlib import Path
import logging
import base64
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.post("/undress-photo-webhook")
async def undress_photo_webhook(
        status: str = Form(...),
        id_gen: str = Form(...),
        time_gen: str = Form(...),
        res_image: UploadFile = File(...),
        img_message: str = Form(None)
):
    try:
        logger.info(f"=== CLOTOFF WEBHOOK ===")
        logger.info(f"Status: {status}")
        logger.info(f"ID Generation: {id_gen}")
        logger.info(f"Time Generation: {time_gen}")
        logger.info(f"Image Message: {img_message}")
        logger.info(f"File: {res_image.filename}, Type: {res_image.content_type}")


        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(res_image.filename).suffix or ".png"
        filename = f"undress_{id_gen}_{timestamp}{file_extension}"

        file_path = UPLOAD_DIR / filename
        content = await res_image.read()

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"✅ File saved: {file_path.absolute()}")
        logger.info(f"Size: {len(content)} bytes")

        return {
            "msg": "ok",
            "id": id_gen,
            "file_path": str(file_path.absolute())
        }

    except Exception as e:
        logger.error(f"❌ Помилка: {e}")
        return {"error": str(e)}


@app.post("/undress-photo-pose-webhook")
async def undress_photo_pose_webhook(request: Request):
    try:
        payload = await request.json()

        generation_id = payload.get("id")
        photo_b64 = payload.get("photo")

        logger.info(f"=== POSE WEBHOOK ===")
        logger.info(f"Generation ID: {generation_id}")
        logger.info(f"Photo base64 length: {len(photo_b64) if photo_b64 else 0}")

        if not generation_id or not photo_b64:
            logger.error("❌ Missing id or photo")
            return {"error": "Missing id or photo"}


        try:
            if "," in photo_b64 and ";base64" in photo_b64:
                photo_b64 = photo_b64.split(",", 1)[1]

            image_bytes = base64.b64decode(photo_b64)
        except Exception as e:
            logger.error(f"❌ Error decoding base64: {e}")
            return {"error": "Invalid base64"}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pose_{generation_id}_{timestamp}.png"

        file_path = UPLOAD_DIR / filename

        with open(file_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"✅ File saved: {file_path.absolute()}")
        logger.info(f"Size: {len(image_bytes)} byte")

        return {
            "msg": "ok",
            "id": generation_id,
            "file_path": str(file_path.absolute())
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return {"error": str(e)}


@app.post("/undress-video-webhook")
async def undress_video_webhook(
        idGeneration: str = Form(...),
        filename: str = Form(None),
        video: UploadFile = File(...)
):
    try:
        logger.info(f"=== VIDEO WEBHOOK ===")
        logger.info(f"Generation ID: {idGeneration}")
        logger.info(f"Filename: {filename}")
        logger.info(f"Video file: {video.filename}, Type: {video.content_type}")


        video_bytes = await video.read()
        logger.info(f"Video size: {len(video_bytes)} байт")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(filename).suffix if filename else ".mp4"
        save_filename = f"video_{idGeneration}_{timestamp}{file_extension}"

        file_path = UPLOAD_DIR / save_filename

        with open(file_path, "wb") as f:
            f.write(video_bytes)

        logger.info(f"✅ Video saved: {file_path.absolute()}")

        return {
            "msg": "ok",
            "id": idGeneration,
            "file_path": str(file_path.absolute()),
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return {"error": str(e)}


@app.post("/undress-video-pose-webhook")
async def undress_video_pose_webhook(
        idGeneration: str = Form(...),
        filename: str = Form(None),
        video: UploadFile = File(...)
):
    try:
        logger.info(f"=== VIDEO POSE WEBHOOK ===")
        logger.info(f"Generation ID: {idGeneration}")
        logger.info(f"Filename: {filename}")
        logger.info(f"Video file: {video.filename}, Type: {video.content_type}")

        video_bytes = await video.read()
        logger.info(f"Video size: {len(video_bytes)} байт")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(filename).suffix if filename else ".mp4"
        save_filename = f"video_pose_{idGeneration}_{timestamp}{file_extension}"

        file_path = UPLOAD_DIR / save_filename

        with open(file_path, "wb") as f:
            f.write(video_bytes)

        logger.info(f"✅ Video with pose saved: {file_path.absolute()}")

        return {
            "msg": "ok",
            "id": idGeneration,
            "file_path": str(file_path.absolute()),
        }

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return {"error": str(e)}

@app.get("/")
async def root():
    return {
        "status": "running",
        "endpoints": [
            "/undress-photo-webhook",
            "/undress-photo-pose-webhook",
            "/undress-video-webhook",
            "/undress-video-pose-webhook"
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1234)
