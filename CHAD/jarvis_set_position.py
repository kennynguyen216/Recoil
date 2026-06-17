import os
import sys
import time
from pathlib import Path

import serial
from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

SERIAL_PORT = os.getenv("JARVIS_SERIAL_PORT", "COM3")
BAUD_RATE = 115200


def clamp(angle):
    return max(0, min(180, int(angle)))


def send(arduino, axis, angle):
    command = f"{axis}{clamp(angle)}"
    print(command)
    arduino.write(f"{command}\n".encode("utf-8"))
    arduino.flush()
    time.sleep(0.4)


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python jarvis_set_position.py PAN [TILT]")
        print("Example: python jarvis_set_position.py 105 82")
        raise SystemExit(2)

    pan = sys.argv[1]
    tilt = sys.argv[2] if len(sys.argv) == 3 else None

    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as arduino:
        time.sleep(2)
        print(f"Connected to {SERIAL_PORT}")
        send(arduino, "P", pan)
        if tilt is not None:
            send(arduino, "T", tilt)


if __name__ == "__main__":
    main()
