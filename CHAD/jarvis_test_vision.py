import os
import time
from pathlib import Path

import cv2
from dotenv import load_dotenv
from google import genai
from PIL import Image


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

CAMERA_INDEX = int(os.getenv("JARVIS_CAMERA_INDEX", "0"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def open_camera(camera_index):
    if os.name == "nt":
        return cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(camera_index)


def analyze_frame(frame):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY.")

    client = genai.Client(api_key=api_key)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    prompt = (
        "Look at this webcam image. If it contains a math equation or written "
        "problem, solve it clearly. Otherwise briefly describe the scene."
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, image],
    )
    return response.text.strip()


def main():
    print(f"Opening camera {CAMERA_INDEX}...")
    camera = open_camera(CAMERA_INDEX)
    if not camera.isOpened():
        raise RuntimeError(f"Camera {CAMERA_INDEX} did not open.")

    try:
        print("Warming camera...")
        for _ in range(20):
            camera.read()
            time.sleep(0.03)

        ok, frame = camera.read()
        if not ok:
            raise RuntimeError("Could not capture a frame.")

        cv2.imwrite("jarvis_vision_test.jpg", frame)
        print("Saved jarvis_vision_test.jpg")
        print("Sending frame to Gemini...")
        print(analyze_frame(frame))
    finally:
        camera.release()


if __name__ == "__main__":
    main()
