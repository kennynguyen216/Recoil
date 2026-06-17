#include <Servo.h>

Servo panServo;
Servo tiltServo;

const int PAN_PIN = 9;
const int TILT_PIN = 10;

int panAngle = 90;
int tiltAngle = 90;
bool servosAttached = false;

void setup() {
  Serial.begin(115200);
  Serial.println("Jarvis Arduino ready");
}

void attachServosIfNeeded() {
  if (servosAttached) {
    return;
  }
  panServo.attach(PAN_PIN);
  tiltServo.attach(TILT_PIN);
  servosAttached = true;
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  char axis = Serial.read();

  if (axis == 'D' || axis == 'd') {
    panServo.detach();
    tiltServo.detach();
    servosAttached = false;
    Serial.println("Detached");
    return;
  }

  if (axis == 'A' || axis == 'a') {
    attachServosIfNeeded();
    Serial.println("Attached");
    return;
  }

  int angle = Serial.parseInt();
  angle = constrain(angle, 0, 180);

  if (axis == 'P' || axis == 'p') {
    attachServosIfNeeded();
    panAngle = angle;
    panServo.write(panAngle);
    Serial.print("P");
    Serial.println(panAngle);
  } else if (axis == 'T' || axis == 't') {
    attachServosIfNeeded();
    tiltAngle = angle;
    tiltServo.write(tiltAngle);
    Serial.print("T");
    Serial.println(tiltAngle);
  }
}
