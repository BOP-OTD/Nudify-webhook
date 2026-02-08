from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True, "note": "Webhook is at /undress-photo-webhook (or rename for cartoonify)"}

@app.post("/undress-photo-webhook")
async def undress_photo_webhook(request: Request):
    content_type = request.headers.get("content-type", "")
    print("CONTENT-TYPE:", content_type)

    # If the provider sends JSON
    if "application/json" in content_type:
        data = await request.json()
        print("WEBHOOK JSON:", data)
        return JSONResponse({"ok": True, "type": "json"})

    # If the provider sends form-data (common for file uploads)
    form = await request.form()
    keys = list(form.keys())
    print("WEBHOOK FORM KEYS:", keys)

    # Identify file fields (if any)
    for k in keys:
        v = form.get(k)
        if hasattr(v, "filename"):
            print(f"FILE FIELD: {k} filename={v.filename} content_type={getattr(v, 'content_type', None)}")

    return JSONResponse({"ok": True, "type": "form", "keys": keys})
