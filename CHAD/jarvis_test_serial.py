import os
import time
from pathlib import Path

import serial
from dotenv import load_dotenv


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

SERIAL_PORT = os.getenv("JARVIS_SERIAL_PORT", "COM3")
BAUD_RATE = 115200


def send(arduino, axis, angle):
    command = f"{axis}{angle}\n"
    print(command.strip())
    arduino.write(command.encode("utf-8"))
    time.sleep(0.6)


def main():
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as arduino:
        time.sleep(2)
        print(f"Connected to {SERIAL_PORT}")

        for pan in (60, 90, 120, 90):
            send(arduino, "P", pan)

        for tilt in (65, 90, 115, 90):
            send(arduino, "T", tilt)

        print("Serial servo test complete.")


if __name__ == "__main__":
    main()
