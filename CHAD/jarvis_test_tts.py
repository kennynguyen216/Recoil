import os
from pathlib import Path

import pyttsx3
from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")


def main():
    engine = pyttsx3.init()
    engine.setProperty("rate", int(os.getenv("JARVIS_TTS_RATE", "165")))
    voices = engine.getProperty("voices")
    print(f"Voices found: {len(voices)}")
    for index, voice in enumerate(voices):
        print(f"{index}: {voice.name} ({voice.id})")

    text = (
        "Jarvis text to speech test. Step one, read the problem. "
        "Step two, solve it carefully. Final answer, the speaker works."
    )
    print("Speaking test phrase...")
    engine.say(text)
    engine.runAndWait()
    engine.stop()
    print("TTS test complete.")


if __name__ == "__main__":
    main()
