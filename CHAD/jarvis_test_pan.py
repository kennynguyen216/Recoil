import os
import time
from pathlib import Path

import serial
from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

SERIAL_PORT = os.getenv("JARVIS_SERIAL_PORT", "COM3")
BAUD_RATE = 115200


def send(arduino, command):
    print(command)
    arduino.write(f"{command}\n".encode("utf-8"))
    arduino.flush()
    time.sleep(1.2)
    while arduino.in_waiting:
        print("Arduino:", arduino.readline().decode("utf-8", errors="replace").strip())


def main():
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as arduino:
        time.sleep(2)
        print(f"Connected to {SERIAL_PORT}")
        for command in ("P30", "P90", "P150", "P90"):
            send(arduino, command)
        print("Pan-only test complete.")


if __name__ == "__main__":
    main()
