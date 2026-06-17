const int SOLENOID_PIN = 9;
const int DEFAULT_RECOIL_MS = 35;
const int VANDAL_RECOIL_MS = 28;
const int PHANTOM_RECOIL_MS = 34;
const int SPECTRE_RECOIL_MS = 24;
const int SHERIFF_RECOIL_MS = 65;
const int OPERATOR_RECOIL_MS = 85;
void setup() {
  pinMode(SOLENOID_PIN, OUTPUT);
  digitalWrite(SOLENOID_PIN, LOW);
  Serial.begin(115200);
  Serial.println("READY");
}
void loop() {
  if (!Serial.available()) {
    return;
  }
  char cmd = Serial.read();
  if (cmd == '\n' || cmd == '\r') {
    return;
  }
  Serial.print("CMD ");
  Serial.println(cmd);
  if (cmd == 'R') {
    fireRecoil(DEFAULT_RECOIL_MS);
  } else if (cmd == 'V') {
    fireRecoil(VANDAL_RECOIL_MS);
  } else if (cmd == 'P') {
    fireRecoil(PHANTOM_RECOIL_MS);
  } else if (cmd == 'S') {
    fireRecoil(SPECTRE_RECOIL_MS);
  } else if (cmd == 'H') {
    fireRecoil(SHERIFF_RECOIL_MS);
  } else if (cmd == 'O') {
    fireRecoil(OPERATOR_RECOIL_MS);
  } else {
    Serial.println("UNKNOWN");
  }
}
void fireRecoil(int recoilMs) {
  Serial.print("KICK ");
  Serial.println(recoilMs);
  digitalWrite(SOLENOID_PIN, HIGH);
  delay(recoilMs);
  digitalWrite(SOLENOID_PIN, LOW);
}