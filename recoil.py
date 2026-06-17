"""
Solenoid recoil feedback controller.

Anti-cheat safety note:
This script only reads pixels from the screen using mss. It never reads game
memory, injects into any process, or hooks game functions. It only sends a
single-byte solenoid recoil command to an Arduino over serial.

Dependencies:
    pynput pyserial mss numpy opencv-python pytesseract
"""

from __future__ import annotations

import argparse
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import mss
import numpy as np
import pytesseract
import serial
from pynput import mouse
from serial import SerialException


# Serial port used by the Arduino Uno.
SERIAL_PORT = "COM3"

# Serial baud rate configured in the Arduino sketch.
BAUD_RATE = 115200

# Active game profile used for screen-region lookup.
ACTIVE_GAME = "valorant"

# Seconds between OCR scans of the weapon HUD region.
OCR_INTERVAL = 2.0

# Hard lower bound between serial recoil commands so the solenoid can retract.
MIN_RECOIL_GAP = 0.10


# All screen regions are configurable here. Coordinates are absolute screen
# pixels for the selected resolution/layout.
GAME_PROFILES = {
    "cs2": {
        # CS2 1080p default weapon name region.
        "weapon_region": {"left": 1650, "top": 1010, "width": 250, "height": 30},
    },
    "valorant": {
        "weapon_region": {"left": 1235, "top": 1000, "width": 300, "height": 120},
    },
}


WEAPON_PROFILES = {
    "Vandal": {
        "base_interval": 0.13,
        "min_interval": 0.11,
        "ramp_speed": 0.004,
        "kick_duration_ms": 42,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"V",
    },
    "Phantom": {
        "base_interval": 0.13,
        "min_interval": 0.11,
        "ramp_speed": 0.004,
        "kick_duration_ms": 34,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"P",
    },
    "Operator": {
        "base_interval": 0.90,
        "min_interval": 0.90,
        "ramp_speed": 0.000,
        "kick_duration_ms": 95,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "semi",
        "recoil_command": b"O",
    },
    "Sheriff": {
        "base_interval": 0.42,
        "min_interval": 0.42,
        "ramp_speed": 0.000,
        "kick_duration_ms": 70,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "semi",
        "recoil_command": b"H",
    },
    "Spectre": {
        "base_interval": 0.105,
        "min_interval": 0.10,
        "ramp_speed": 0.002,
        "kick_duration_ms": 22,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"S",
    },
    "AK47": {
        "base_interval": 0.10,
        "min_interval": 0.04,
        "ramp_speed": 0.012,
        "kick_duration_ms": 40,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"R",
    },
    "AWP": {
        "base_interval": 0.80,
        "min_interval": 0.80,
        "ramp_speed": 0.000,
        "kick_duration_ms": 80,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "semi",
        "recoil_command": b"O",
    },
    "M4A4": {
        "base_interval": 0.09,
        "min_interval": 0.04,
        "ramp_speed": 0.010,
        "kick_duration_ms": 35,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"V",
    },
    "M4A1S": {
        "base_interval": 0.10,
        "min_interval": 0.04,
        "ramp_speed": 0.009,
        "kick_duration_ms": 35,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"P",
    },
    "Pistol": {
        "base_interval": 0.20,
        "min_interval": 0.12,
        "ramp_speed": 0.005,
        "kick_duration_ms": 25,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "semi",
        "recoil_command": b"R",
    },
    "MP5/SMG": {
        "base_interval": 0.07,
        "min_interval": 0.04,
        "ramp_speed": 0.006,
        "kick_duration_ms": 20,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"S",
    },
    "Deagle": {
        "base_interval": 0.40,
        "min_interval": 0.40,
        "ramp_speed": 0.000,
        "kick_duration_ms": 60,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "semi",
        "recoil_command": b"H",
    },
    "Default": {
        "base_interval": 0.14,
        "min_interval": 0.05,
        "ramp_speed": 0.008,
        "kick_duration_ms": 30,
        "pulse_count": 1,
        "pulse_gap": 0.0,
        "fire_mode": "auto",
        "recoil_command": b"R",
    },
}


WEAPON_ALIASES = {
    "Vandal": ("vandal",),
    "Phantom": ("phantom",),
    "Operator": ("operator", "op"),
    "Sheriff": ("sheriff",),
    "Spectre": ("spectre",),
    "AK47": ("ak47", "ak-47", "ak 47", "ak"),
    "AWP": ("awp",),
    "M4A4": ("m4a4", "m4 a4"),
    "M4A1S": ("m4a1s", "m4a1-s", "m4a1", "m4 a1"),
    "Pistol": ("pistol", "glock", "usp", "p2000", "classic", "ghost"),
    "MP5/SMG": ("mp5", "smg", "stinger", "mac10", "mp9", "ump"),
    "Deagle": ("deagle", "desert eagle"),
}


# The only mutable shared application state requested by the design.
active_profile = WEAPON_PROFILES["Vandal"]
serial_connection: Optional[serial.Serial] = None


@dataclass(frozen=True)
class RecoilCommandSender:
    dry_run: bool

    def send_recoil(self, command: bytes = b"R") -> None:
        if self.dry_run:
            print(f"DRY RUN: {command.decode('ascii')}")
            return

        if serial_connection is None or not serial_connection.is_open:
            return

        try:
            serial_connection.write(command)
        except SerialException as exc:
            print(f"Serial write failed: {exc}")


class RecoilController:
    def __init__(self, sender: RecoilCommandSender) -> None:
        self.sender = sender
        self.stop_firing = threading.Event()
        self.shutdown = threading.Event()
        self._lock = threading.Lock()
        self._firing_thread: Optional[threading.Thread] = None
        self._last_recoil_at = 0.0

    def press(self) -> None:
        profile = active_profile

        with self._lock:
            if profile.get("fire_mode") == "semi":
                self._fire_semi_locked(profile)
                return

            if self._firing_thread and self._firing_thread.is_alive():
                return

            self.stop_firing.clear()
            self._firing_thread = threading.Thread(
                target=self._fire_loop,
                name="recoil-fire-loop",
                daemon=True,
            )
            self._firing_thread.start()

    def release(self) -> None:
        self.stop_firing.set()

    def stop(self) -> None:
        self.shutdown.set()
        self.stop_firing.set()
        thread = self._firing_thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)

    def _fire_loop(self) -> None:
        profile = active_profile
        interval = profile["base_interval"]

        while not self.shutdown.is_set() and not self.stop_firing.is_set():
            self._send_profile_recoil(profile)

            safe_interval = max(interval, MIN_RECOIL_GAP)
            if self.stop_firing.wait(safe_interval):
                break

            interval = max(
                profile["min_interval"],
                interval - profile["ramp_speed"],
            )

    def _fire_semi_locked(self, profile: dict[str, object]) -> None:
        now = time.monotonic()
        ready_at = self._last_recoil_at + max(float(profile["base_interval"]), MIN_RECOIL_GAP)

        if now < ready_at:
            return

        self._send_profile_recoil(profile)

    def _send_profile_recoil(self, profile: dict[str, object]) -> None:
        self._last_recoil_at = time.monotonic()
        pulse_count = int(profile.get("pulse_count", 1))
        pulse_gap = float(profile.get("pulse_gap", 0.0))
        command = profile.get("recoil_command", b"R")

        for pulse_index in range(pulse_count):
            self.sender.send_recoil(command)
            if pulse_index < pulse_count - 1 and self.stop_firing.wait(pulse_gap):
                break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send Arduino recoil commands from mouse input and OCR weapon detection."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip serial connection and print R commands instead.",
    )
    parser.add_argument(
        "--weapon",
        choices=sorted(WEAPON_PROFILES),
        help="Force a weapon profile for demos and skip OCR detection.",
    )
    return parser.parse_args()


def connect_serial(dry_run: bool) -> Optional[serial.Serial]:
    global serial_connection

    if dry_run:
        print("DRY RUN: serial connection skipped")
        return None

    try:
        serial_connection = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2.0)
        print("READY")
        return serial_connection
    except SerialException as exc:
        print(f"Could not connect to Arduino on {SERIAL_PORT}: {exc}")
        print("Run with --dry-run to test mouse input and OCR without hardware.")
        return None


def get_weapon_region() -> Optional[dict[str, int]]:
    game_profile = GAME_PROFILES.get(ACTIVE_GAME)
    if game_profile is None:
        return None

    return game_profile["weapon_region"]


def normalize_ocr_text(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^a-z0-9+\- ]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def compact_match_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def match_weapon_profile(ocr_text: str) -> Optional[str]:
    normalized = normalize_ocr_text(ocr_text)
    compact = compact_match_text(normalized)

    if not normalized:
        return None

    for profile_name, aliases in WEAPON_ALIASES.items():
        for alias in aliases:
            alias_normalized = alias.lower()
            alias_compact = compact_match_text(alias_normalized)
            if alias_normalized in normalized or alias_compact in compact:
                return profile_name

    return None


def ocr_weapon_detector(stop_event: threading.Event, enabled: bool = True) -> None:
    global active_profile

    if not enabled:
        return

    weapon_region = get_weapon_region()
    if weapon_region is None:
        print(f"OCR disabled: unknown ACTIVE_GAME '{ACTIVE_GAME}'")
        return

    current_profile_name = get_profile_name(active_profile)
    ocr_warning_printed = False

    with mss.MSS() as screen_capture:
        while not stop_event.is_set():
            try:
                screenshot = screen_capture.grab(weapon_region)
                image = np.array(screenshot)
                grayscale = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
                _, binary = cv2.threshold(grayscale, 150, 255, cv2.THRESH_BINARY)
                raw_text = pytesseract.image_to_string(binary, config="--psm 7")
                matched_profile_name = match_weapon_profile(raw_text)

                if matched_profile_name and matched_profile_name != current_profile_name:
                    active_profile = WEAPON_PROFILES[matched_profile_name]
                    current_profile_name = matched_profile_name
                    print(f"Detected weapon: {matched_profile_name}")
                    print(f"Recoil feel: {describe_profile(active_profile)}")
            except pytesseract.TesseractNotFoundError:
                if not ocr_warning_printed:
                    print(
                        "OCR disabled: Tesseract is not installed or is not in PATH. "
                        "Use --weapon for demos, or install Tesseract OCR to enable detection."
                    )
                    ocr_warning_printed = True
                return
            except Exception as exc:
                print(f"OCR scan failed: {exc}")

            stop_event.wait(OCR_INTERVAL)


def build_mouse_listener(controller: RecoilController) -> mouse.Listener:
    def on_click(_x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if button != mouse.Button.left:
            return

        if pressed:
            controller.press()
        else:
            controller.release()

    return mouse.Listener(on_click=on_click)


def close_serial() -> None:
    if serial_connection is None:
        return

    try:
        if serial_connection.is_open:
            serial_connection.close()
            print("Serial port closed")
    except SerialException as exc:
        print(f"Serial close failed: {exc}")


def get_profile_name(profile: dict[str, float]) -> str:
    for profile_name, candidate in WEAPON_PROFILES.items():
        if candidate is profile:
            return profile_name

    return "Unknown"


def describe_profile(profile: dict[str, float]) -> str:
    pulses = int(profile.get("pulse_count", 1))
    return (
        f"{pulses} pulse(s), "
        f"{profile.get('recoil_command', b'R').decode('ascii')} command, "
        f"{profile['base_interval']:.3f}s base, "
        f"{profile['min_interval']:.3f}s min, "
        f"{profile['kick_duration_ms']}ms kick"
    )


# TODO: TENS integration
# Future HP monitoring and zap logic should live in its own controller/thread
# here. It should use separate explicit serial commands and independent stop
# signals. This version intentionally implements solenoid recoil only, and sends
# no TENS, zap, HP-monitoring, damage-detection, Z, or X commands.


def main() -> int:
    global active_profile

    args = parse_args()

    if args.weapon:
        active_profile = WEAPON_PROFILES[args.weapon]

    print(f"Serial port: {SERIAL_PORT} @ {BAUD_RATE}")
    print(f"Active game: {ACTIVE_GAME}")
    print(f"Current weapon profile: {get_profile_name(active_profile)}")
    print(f"Recoil feel: {describe_profile(active_profile)}")
    if args.weapon:
        print("OCR disabled: using forced weapon profile")

    if ACTIVE_GAME not in GAME_PROFILES:
        print(f"Unknown ACTIVE_GAME '{ACTIVE_GAME}'. Available: {', '.join(GAME_PROFILES)}")
        return 2

    connection = connect_serial(args.dry_run)
    if connection is None and not args.dry_run:
        return 1

    shutdown = threading.Event()
    sender = RecoilCommandSender(dry_run=args.dry_run)
    controller = RecoilController(sender)
    ocr_thread = threading.Thread(
        target=ocr_weapon_detector,
        args=(shutdown, args.weapon is None),
        name="weapon-ocr-detector",
        daemon=True,
    )

    listener = build_mouse_listener(controller)

    try:
        ocr_thread.start()
        listener.start()
        print("Listening for left mouse recoil input...")

        while listener.running:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        shutdown.set()
        controller.stop()
        listener.stop()
        listener.join(timeout=1.0)
        ocr_thread.join(timeout=2.0)
        close_serial()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
