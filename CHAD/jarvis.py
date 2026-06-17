import json
import os
import re
import threading
import time
from pathlib import Path

import cv2
import pyttsx3
import serial
import speech_recognition as sr
from dotenv import load_dotenv
from google import genai
from PIL import Image


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

SERIAL_PORT = os.getenv("JARVIS_SERIAL_PORT", "COM3")
BAUD_RATE = 115200
CAMERA_INDEX = int(os.getenv("JARVIS_CAMERA_INDEX", "0"))
MIC_INDEX = os.getenv("JARVIS_MIC_INDEX")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SHOW_CAMERA_PREVIEW = os.getenv("SHOW_CAMERA_PREVIEW", "true").lower() == "true"
INVERT_PAN = os.getenv("JARVIS_INVERT_PAN", "true").lower() == "true"
INVERT_TILT = os.getenv("JARVIS_INVERT_TILT", "false").lower() == "true"
TTS_BACKEND = os.getenv("JARVIS_TTS_BACKEND", "sapi" if os.name == "nt" else "pyttsx3")
PRESETS_PATH = Path("jarvis_presets.json")
SOLVE_IMAGE_PATH = Path("jarvis_solve_capture.jpg")

PAN_MIN = 0
PAN_MAX = 180
TILT_MIN = 35
TILT_MAX = 145
HOME_PAN = int(os.getenv("JARVIS_HOME_PAN", "90"))
HOME_TILT = int(os.getenv("JARVIS_HOME_TILT", "90"))
STEP_SIZE = int(os.getenv("JARVIS_STEP_SIZE", "30"))
FAR_STEP_SIZE = int(os.getenv("JARVIS_FAR_STEP_SIZE", "60"))
PAN_STEP_SIZE = int(os.getenv("JARVIS_PAN_STEP_SIZE", str(STEP_SIZE)))
TILT_STEP_SIZE = int(os.getenv("JARVIS_TILT_STEP_SIZE", str(STEP_SIZE)))
PAN_FAR_STEP_SIZE = int(os.getenv("JARVIS_PAN_FAR_STEP_SIZE", str(FAR_STEP_SIZE)))
TILT_FAR_STEP_SIZE = int(os.getenv("JARVIS_TILT_FAR_STEP_SIZE", str(FAR_STEP_SIZE)))


class Jarvis:
    def __init__(self):
        self.pan = HOME_PAN
        self.tilt = HOME_TILT
        self.presets = self.load_presets()
        self.recognizer = sr.Recognizer()
        self.microphone = self.connect_microphone()
        self.arduino = self.connect_arduino()
        self.camera = self.connect_camera()
        self.camera_lock = threading.Lock()
        self.last_frame = None
        self.preview_running = False
        self.preview_thread = None
        self.start_camera_preview()
        self.model = self.connect_gemini()

    def connect_arduino(self):
        try:
            arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            print(f"Connected to Arduino on {SERIAL_PORT}")
            print(f"Moving to home position: P{self.pan} T{self.tilt}")
            self.send_servo_position("P", self.pan, arduino)
            self.send_servo_position("T", self.tilt, arduino)
            time.sleep(0.5)
            return arduino
        except serial.SerialException as exc:
            print(f"Arduino connection failed on {SERIAL_PORT}: {exc}")
            print("Movement commands will be ignored until the port is fixed.")
            return None

    def connect_microphone(self):
        if MIC_INDEX is None or MIC_INDEX == "":
            print("Using default Windows microphone.")
            return sr.Microphone()

        index = int(MIC_INDEX)
        names = sr.Microphone.list_microphone_names()
        name = names[index] if 0 <= index < len(names) else "unknown microphone"
        print(f"Using microphone {index}: {name}")
        return sr.Microphone(device_index=index)

    def connect_camera(self):
        camera = open_camera(CAMERA_INDEX)
        if not camera.isOpened():
            print(f"Camera {CAMERA_INDEX} did not open. Vision commands will fail.")
            return None
        return camera

    def connect_gemini(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing GOOGLE_API_KEY. Set it first, then run: python jarvis.py"
            )
        return genai.Client(api_key=api_key)

    def load_presets(self):
        if not PRESETS_PATH.exists():
            return {}
        with PRESETS_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_presets(self):
        with PRESETS_PATH.open("w", encoding="utf-8") as handle:
            json.dump(self.presets, handle, indent=2)

    def speak(self, text):
        spoken_text = clean_tts_text(text)
        print(f"Jarvis: {text}")
        chunks = chunk_text(spoken_text)
        if TTS_BACKEND == "sapi" and os.name == "nt":
            if speak_with_sapi(chunks):
                return

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", int(os.getenv("JARVIS_TTS_RATE", "165")))
            for chunk in chunks:
                print(f"Speaking chunk: {chunk}")
                engine.say(chunk)
            engine.runAndWait()
            engine.stop()
        except Exception as exc:
            print(f"TTS failed: {exc}")

    def listen(self):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
            print("Listening...")
            audio = self.recognizer.listen(source)

        try:
            text = self.recognizer.recognize_google(audio).lower()
            print(f"You: {text}")
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            print(f"Speech recognition failed: {exc}")
            return ""

    def clamp(self, value, lower, upper):
        return max(lower, min(upper, value))

    def send_servo_position(self, axis, angle, arduino=None):
        target = arduino or self.arduino
        if target is None:
            print(f"Skipped {axis}{int(angle)} because Arduino is not connected.")
            return False
        command = f"{axis}{int(angle)}\n"
        print(f"Sending servo command: {command.strip()}")
        try:
            target.write(command.encode("utf-8"))
            target.flush()
            time.sleep(0.08)
            return True
        except serial.SerialException as exc:
            print(f"Servo command failed: {exc}")
            return False

    def set_position(self, pan=None, tilt=None):
        moved = False
        if pan is not None:
            self.pan = self.clamp(pan, PAN_MIN, PAN_MAX)
            moved = self.send_servo_position("P", self.pan) or moved
        if tilt is not None:
            self.tilt = self.clamp(tilt, TILT_MIN, TILT_MAX)
            moved = self.send_servo_position("T", self.tilt) or moved
        return moved

    def handle_movement(self, command):
        pan_left_delta = PAN_STEP_SIZE if INVERT_PAN else -PAN_STEP_SIZE
        pan_right_delta = -PAN_STEP_SIZE if INVERT_PAN else PAN_STEP_SIZE
        far_left_delta = PAN_FAR_STEP_SIZE if INVERT_PAN else -PAN_FAR_STEP_SIZE
        far_right_delta = -PAN_FAR_STEP_SIZE if INVERT_PAN else PAN_FAR_STEP_SIZE
        tilt_up_delta = TILT_STEP_SIZE if INVERT_TILT else -TILT_STEP_SIZE
        tilt_down_delta = -TILT_STEP_SIZE if INVERT_TILT else TILT_STEP_SIZE
        far_up_delta = TILT_FAR_STEP_SIZE if INVERT_TILT else -TILT_FAR_STEP_SIZE
        far_down_delta = -TILT_FAR_STEP_SIZE if INVERT_TILT else TILT_FAR_STEP_SIZE

        pan_match = re.search(r"(?:set )?(?:pan|left right|left and right)(?: servo)?(?: to)? (\d{1,3})", command)
        if pan_match:
            angle = int(pan_match.group(1))
            moved = self.set_position(pan=angle)
            self.speak(f"Pan set to {self.pan} degrees." if moved else "I heard you, but Arduino is not connected.")
            return True

        tilt_match = re.search(r"(?:set )?(?:tilt|up down|up and down)(?: servo)?(?: to)? (\d{1,3})", command)
        if tilt_match:
            angle = int(tilt_match.group(1))
            moved = self.set_position(tilt=angle)
            self.speak(f"Tilt set to {self.tilt} degrees." if moved else "I heard you, but Arduino is not connected.")
            return True

        both_match = re.search(r"(?:set )?(?:position|camera)(?: to)? (\d{1,3}) (?:and )?(\d{1,3})", command)
        if both_match:
            pan = int(both_match.group(1))
            tilt = int(both_match.group(2))
            moved = self.set_position(pan=pan, tilt=tilt)
            self.speak(
                f"Position set to pan {self.pan}, tilt {self.tilt}."
                if moved
                else "I heard you, but Arduino is not connected."
            )
            return True

        if "far left" in command or "hard left" in command:
            moved = self.set_position(pan=self.pan + far_left_delta)
            self.speak("Looking far left." if moved else "I heard you, but Arduino is not connected.")
            return True
        if "far right" in command or "hard right" in command:
            moved = self.set_position(pan=self.pan + far_right_delta)
            self.speak("Looking far right." if moved else "I heard you, but Arduino is not connected.")
            return True
        if "far up" in command or "all the way up" in command:
            moved = self.set_position(tilt=self.tilt + far_up_delta)
            self.speak("Looking far up." if moved else "I heard you, but Arduino is not connected.")
            return True
        if "far down" in command or "all the way down" in command:
            moved = self.set_position(tilt=self.tilt + far_down_delta)
            self.speak("Looking far down." if moved else "I heard you, but Arduino is not connected.")
            return True
        if (
            "home" in command
            or "neutral" in command
            or "reset position" in command
            or "fixed state" in command
        ):
            moved = self.set_position(pan=HOME_PAN, tilt=HOME_TILT)
            self.speak("Back to neutral." if moved else "I heard you, but Arduino is not connected.")
            return True
        if "left" in command or "pan left" in command:
            moved = self.set_position(pan=self.pan + pan_left_delta)
            self.speak("Looking left." if moved else "I heard you, but Arduino is not connected.")
            return True
        if "right" in command or "rite" in command or "write" in command or "pan right" in command:
            moved = self.set_position(pan=self.pan + pan_right_delta)
            self.speak("Looking right." if moved else "I heard you, but Arduino is not connected.")
            return True
        if (
            "look up" in command
            or "tilt up" in command
            or "move up" in command
            or "raise camera" in command
        ):
            moved = self.set_position(tilt=self.tilt + tilt_up_delta)
            self.speak("Looking up." if moved else "I heard you, but Arduino is not connected.")
            return True
        if (
            "look down" in command
            or "tilt down" in command
            or "move down" in command
            or "lower camera" in command
        ):
            moved = self.set_position(tilt=self.tilt + tilt_down_delta)
            self.speak("Looking down." if moved else "I heard you, but Arduino is not connected.")
            return True
        if "center" in command or "straight ahead" in command:
            moved = self.set_position(pan=HOME_PAN, tilt=HOME_TILT)
            self.speak("Centered." if moved else "I heard you, but Arduino is not connected.")
            return True
        return False

    def handle_preset(self, command):
        save_match = re.search(r"save (?:this )?(?:position )?(?:as )?([a-z0-9 _-]+)", command)
        if save_match:
            name = save_match.group(1).strip()
            self.presets[name] = {"pan": self.pan, "tilt": self.tilt}
            self.save_presets()
            self.speak(f"Saved {name}.")
            return True

        go_match = re.search(r"(?:go to|load|use) (?:preset )?([a-z0-9 _-]+)", command)
        if go_match:
            name = go_match.group(1).strip()
            preset = self.presets.get(name)
            if not preset:
                self.speak(f"I do not have a preset named {name}.")
                return True
            self.set_position(pan=preset["pan"], tilt=preset["tilt"])
            self.speak(f"Moved to {name}.")
            return True

        return False

    def capture_frame(self):
        if self.camera is None:
            raise RuntimeError("Camera is not connected.")

        if self.preview_running:
            for _ in range(30):
                if self.last_frame is not None:
                    return self.last_frame.copy()
                time.sleep(0.03)

        with self.camera_lock:
            for _ in range(8):
                self.camera.read()
                time.sleep(0.03)

            ok, frame = self.camera.read()
            if not ok:
                raise RuntimeError("Could not capture a webcam frame.")
            return frame

    def start_camera_preview(self):
        if not SHOW_CAMERA_PREVIEW or self.camera is None:
            return

        self.preview_running = True
        self.preview_thread = threading.Thread(target=self.camera_preview_loop, daemon=True)
        self.preview_thread.start()

    def camera_preview_loop(self):
        window_name = "Jarvis Webcam POV"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        while self.preview_running:
            with self.camera_lock:
                ok, frame = self.camera.read()

            if ok:
                self.last_frame = frame.copy()
                cv2.imshow(window_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                self.preview_running = False
                break

            time.sleep(0.01)

        cv2.destroyWindow(window_name)

    def edge_score(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        return float(edges.mean())

    def scan_for_best_frame(self):
        original_pan = self.pan
        original_tilt = self.tilt
        best_frame = None
        best_score = -1

        for pan in (45, 65, 90, 115, 135):
            self.set_position(pan=pan, tilt=original_tilt)
            time.sleep(0.35)
            frame = self.capture_frame()
            score = self.edge_score(frame)
            if score > best_score:
                best_score = score
                best_frame = frame

        self.set_position(pan=original_pan, tilt=original_tilt)
        return best_frame

    def scan_board_for_equation(self):
        original_pan = self.pan
        original_tilt = self.tilt
        candidates = []
        positions = [
            (60, 75),
            (90, 75),
            (120, 75),
            (60, 95),
            (90, 95),
            (120, 95),
            (60, 115),
            (90, 115),
            (120, 115),
        ]

        for index, (pan, tilt) in enumerate(positions, start=1):
            self.set_position(pan=pan, tilt=tilt)
            time.sleep(0.45)
            frame = self.capture_frame()
            score = self.edge_score(frame)
            path = Path(f"jarvis_board_scan_{index}.jpg")
            cv2.imwrite(str(path), frame)
            print(f"Board scan frame {index}: P{pan} T{tilt}, edge score {score:.2f}, saved {path}")
            candidates.append((score, frame, path, pan, tilt))

        self.set_position(pan=original_pan, tilt=original_tilt)
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[:3]

    def analyze_frame(self, frame, mode="describe"):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        if mode == "solve":
            prompt = (
                "You are Jarvis looking at a math problem through a webcam. Read the "
                "equation or written problem in the image. Give a spoken answer only: "
                "two or three brief steps and one concise final answer sentence. Keep "
                "it under 60 words. Do not greet the user. Avoid markdown and long "
                "symbol dumps. If the image is too blurry or cut off, say what needs "
                "to be adjusted."
            )
        else:
            prompt = (
                "You are Jarvis looking through a webcam. If the image contains a math "
                "equation or written problem, solve it step by step and give the final "
                "answer clearly. If there is no equation, briefly describe what you see."
            )
        response = self.model.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, image],
        )
        return response.text.strip()

    def handle_solve(self, command):
        solve_phrases = (
            "solve",
            "answer",
            "calculate",
            "do the math",
            "math problem",
            "read problem",
            "read the problem",
            "do this problem",
            "figure this out",
        )
        if not any(phrase in command for phrase in solve_phrases):
            return False

        self.speak("Solving.")
        try:
            frame = self.capture_frame()
            cv2.imwrite(str(SOLVE_IMAGE_PATH), frame)
            print(f"Saved solve capture: {SOLVE_IMAGE_PATH}")
            answer = self.analyze_frame(frame, mode="solve")
            self.speak(answer)
        except Exception as exc:
            self.speak(f"I could not solve it. {exc}")
        return True

    def handle_board_scan(self, command):
        board_scan_phrases = (
            "scan board",
            "scan the board",
            "find equation",
            "find the equation",
            "look for equation",
            "look for the equation",
            "search board",
            "search the board",
        )
        if not any(phrase in command for phrase in board_scan_phrases):
            return False

        self.speak("Scanning the board for an equation.")
        try:
            candidates = self.scan_board_for_equation()
            best_frame = candidates[0][1]
            cv2.imwrite(str(SOLVE_IMAGE_PATH), best_frame)
            answer = self.analyze_frame(best_frame, mode="solve")
            self.speak(answer)
        except Exception as exc:
            self.speak(f"I could not scan the board. {exc}")
        return True

    def handle_vision(self, command):
        vision_phrases = (
            "scan",
            "what do you see",
            "what's in front of you",
            "describe what you see",
            "read this",
            "solve this",
        )
        if not any(phrase in command for phrase in vision_phrases):
            return False

        self.speak("Scanning.")
        try:
            frame = self.scan_for_best_frame() if "scan" in command else self.capture_frame()
            answer = self.analyze_frame(frame)
            self.speak(answer)
        except Exception as exc:
            self.speak(f"I could not complete the vision scan. {exc}")
        return True

    def handle_command(self, command):
        if not command:
            return

        if self.is_shutdown_command(command):
            self.speak("Shutting down.")
            raise KeyboardInterrupt

        if self.handle_movement(command):
            return
        if self.handle_preset(command):
            return
        if self.handle_board_scan(command):
            return
        if self.handle_solve(command):
            return
        if self.handle_vision(command):
            return

        self.speak("I heard you, but I do not know that command yet.")

    def run(self):
        self.speak("Jarvis online.")
        while True:
            heard = self.listen()
            if not heard:
                continue

            if self.is_shutdown_command(heard):
                self.handle_command(heard)

            if "jarvis" not in heard:
                print("Wake word not heard; ignoring command.")
                continue

            command = heard.replace("jarvis", "", 1).strip()
            print(f"Command routed to handler: {command}")
            self.handle_command(command)

    def is_shutdown_command(self, command):
        return (
            "stop listening" in command
            or "shut down" in command
            or "exit" in command
            or "quit" in command
        )

    def close(self):
        self.preview_running = False
        if self.preview_thread is not None:
            self.preview_thread.join(timeout=1)
        if self.camera is not None:
            self.camera.release()
        if self.arduino is not None:
            self.arduino.close()


def open_camera(camera_index):
    if os.name == "nt":
        return cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(camera_index)


def clean_tts_text(text):
    text = re.sub(r"[*_`#>\[\]{}]", "", str(text))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text, max_length=160):
    if not text:
        return []

    chunks = []
    current = ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_length:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def speak_with_sapi(chunks):
    try:
        import win32com.client

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Rate = int(os.getenv("JARVIS_TTS_RATE_SAPI", "0"))
        for chunk in chunks:
            print(f"Speaking chunk: {chunk}")
            voice.Speak(chunk)
        return True
    except Exception as exc:
        print(f"SAPI TTS failed, falling back to pyttsx3: {exc}")
        return False


if __name__ == "__main__":
    jarvis = None
    try:
        jarvis = Jarvis()
        jarvis.run()
    except KeyboardInterrupt:
        print("Goodbye.")
    finally:
        if jarvis is not None:
            jarvis.close()
