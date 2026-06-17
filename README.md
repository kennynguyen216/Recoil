# Recoil and Jarvis Hardware Prototypes

Two experimental hardware/software prototypes built around Python, Arduino, computer vision, voice input, and serial control.

This repository is intentionally marked as a work in progress. The projects are functional prototypes rather than packaged products, but they show hands-on experience with hardware integration, real-time input, serial protocols, camera pipelines, and AI-assisted interaction.

## Projects

### Solenoid Recoil Feedback

A Python controller and Arduino sketch for translating mouse input and detected weapon profiles into timed solenoid pulses. The goal is to prototype physical recoil feedback for games using a safe serial-command layer instead of touching game memory or injecting into a process.

**Highlights**

- Reads left-click input and sends serial recoil commands to an Arduino.
- Supports different recoil profiles for weapons such as Vandal, Phantom, Spectre, Operator, Sheriff, AK-47, AWP, and M4 variants.
- Can run in `--dry-run` mode for demos without hardware.
- Uses screen OCR as an experimental weapon-detection path.
- Keeps the hardware command protocol simple: one-byte commands mapped to pulse durations on the Arduino.

**Main files**

- `recoil.py`: Python controller for mouse input, OCR, profile selection, and serial output.
- `arduino_solenoid_recoil.ino`: Arduino sketch that receives recoil commands and drives the solenoid pin.

### Jarvis Vision Assistant

A webcam, microphone, text-to-speech, and pan/tilt servo assistant prototype. Jarvis listens for a wake word, moves a camera mount through Arduino serial commands, captures images, and can send frames to Gemini for visual description or math-problem solving.

**Highlights**

- Voice command loop with wake-word routing.
- Pan/tilt servo control through Arduino serial messages.
- Camera preview and frame capture with OpenCV.
- Gemini vision calls for image understanding and math-problem solving.
- Configurable microphone, camera, servo positions, and TTS settings through environment variables.

**Main files**

- `CHAD/jarvis.py`: Main Jarvis Python application.
- `CHAD/jarvis_arduino.ino`: Arduino sketch for pan/tilt servo control.
- `CHAD/.env.example`: Example local configuration.
- `CHAD/jarvis_test_*.py`: Small hardware and subsystem test scripts.

## Tech Stack

- Python
- Arduino / C++
- OpenCV
- PySerial
- SpeechRecognition
- pyttsx3 / Windows SAPI
- Google Gemini API
- MSS, NumPy, Pytesseract

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For Jarvis, copy the example environment file and add your local values:

```bash
copy CHAD\.env.example CHAD\.env
```

Important environment variables:

- `GOOGLE_API_KEY`: Gemini API key for Jarvis vision features.
- `JARVIS_SERIAL_PORT`: Arduino serial port, for example `COM3`.
- `JARVIS_CAMERA_INDEX`: OpenCV camera index.
- `JARVIS_MIC_INDEX`: Optional microphone device index.

## Running

Run the recoil feedback controller without hardware:

```bash
python recoil.py --dry-run --weapon Vandal
```

Run with Arduino hardware connected:

```bash
python recoil.py --weapon Vandal
```

Run Jarvis:

```bash
python CHAD\jarvis.py
```

## Prototype Status

These projects are still evolving. Current limitations include hardware-specific serial ports, calibration-dependent camera/microphone behavior, experimental OCR weapon detection, and a local `.env` configuration workflow. The next cleanup step would be separating hardware configuration into typed config objects and adding mocked tests around serial command generation.

## Safety and Ethics

The recoil prototype is designed as a hardware feedback experiment. The Python controller reads screen pixels and mouse input and sends simple serial commands to an Arduino; it does not read game memory, inject code, or hook game processes.

