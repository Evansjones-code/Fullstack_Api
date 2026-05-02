import uuid
import os
from io import BytesIO
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

# The local folder where images will be stored
UPLOAD_DIR = "static/profile_pics"

def process_profile_image(content: bytes) -> tuple[bytes, str]:
    """
    Processes raw image bytes: auto-orients, crops to 300x300, and converts to JPEG.
    Returns a tuple of (processed_bytes, filename).
    """
    with Image.open(BytesIO(content)) as original:
        # Correct orientation based on EXIF
        img = ImageOps.exif_transpose(original)

        # Center crop and resize to 300x300
        img = ImageOps.fit(img, (300, 300), method=Image.Resampling.LANCZOS)

        # Ensure RGB mode (removes transparency for JPEG compatibility)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        # Generate a unique filename
        filename = f"{uuid.uuid4().hex}.jpg"

        output = BytesIO()
        img.save(output, "JPEG", quality=85, optimize=True)
        processed_bytes = output.getvalue()

    return processed_bytes, filename

def _save_locally(file_bytes: bytes, filename: str) -> None:
    """
    Saves the processed bytes to the local filesystem.
    """
    # Create the directory if it doesn't exist
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

def _delete_locally(filename: str) -> None:
    """
    Deletes an image file from the local filesystem.
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path) and filename != "default.jpg":
        try:
            os.remove(file_path)
        except OSError:
            pass

async def upload_profile_image(file_bytes: bytes, filename: str) -> None:
    """
    Asynchronously handles the local file write.
    """
    await run_in_threadpool(_save_locally, file_bytes, filename)

async def delete_profile_image(filename: str | None) -> None:
    """
    Asynchronously handles the local file deletion.
    """
    if not filename or filename == "default.jpg":
        return
    await run_in_threadpool(_delete_locally, filename)
