import os
import time
from pathlib import Path

import serial
from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

SERIAL_PORT = os.getenv("JARVIS_SERIAL_PORT", "COM3")
BAUD_RATE = 115200


def main():
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as arduino:
        time.sleep(2)
        arduino.write(b"D\n")
        arduino.flush()
        time.sleep(0.2)
        print("Detach command sent.")


if __name__ == "__main__":
    main()
