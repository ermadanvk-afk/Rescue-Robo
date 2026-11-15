#include <ESP32Servo.h>

// =====================================
// MOTOR DRIVER - L298N
// =====================================
#define ENA 32
#define IN1 18
#define IN2 19
#define IN3 25
#define IN4 26
#define ENB 33

// =====================================
// ULTRASONIC SENSOR
// =====================================
#define TRIG_PIN 5
#define ECHO_PIN 27

// =====================================
// SERVO
// =====================================
#define SERVO_PIN 13
Servo scanner;

// =====================================
// FLAME SENSOR HW-491
// =====================================
#define FLAME_AO 34
#define FLAME_DO 35
#define FLAME_ACTIVE HIGH

// =====================================
// SENSOR & SAFETY SETTINGS
// =====================================
const float OBSTACLE_DISTANCE = 25.0; // cm
const float OPEN_DISTANCE = 400.0;    // cm
const unsigned long SAFETY_TIMEOUT_MS = 1500; // Auto-stop if no command received

// State tracking
bool lastFlameState = false;
unsigned long lastCommandTime = 0;
unsigned long lastTelemetryTime = 0;
String currentMovement = "STOP";

// =====================================
// FLAME SENSOR FUNCTION
// =====================================
bool flameDetected() {
  return digitalRead(FLAME_DO) == FLAME_ACTIVE;
}

// =====================================
// ULTRASONIC SENSOR FUNCTION
// =====================================
float getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(5);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout (~5m)
  if (duration == 0) {
    return OPEN_DISTANCE;
  }
  return duration * 0.0343 / 2.0;
}

// =====================================
// MOTOR CONTROL
// =====================================
void enableMotors() {
  digitalWrite(ENA, HIGH);
  digitalWrite(ENB, HIGH);
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  currentMovement = "STOP";
}

void forward() {
  enableMotors();
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  currentMovement = "FORWARD";
}

void backward() {
  enableMotors();
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  currentMovement = "BACKWARD";
}

void turnLeft() {
  enableMotors();
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  currentMovement = "LEFT";
}

void turnRight() {
  enableMotors();
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  currentMovement = "RIGHT";
}

// =====================================
// COMMAND PROCESSOR (FROM RASPBERRY PI)
// =====================================
void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd.length() == 0) return;

  lastCommandTime = millis();

  // Note: Commands from Raspberry Pi are always executed directly
  // and never overwritten, allowing operator control even during alerts.
  if (cmd == "F" || cmd == "FORWARD" || cmd == "FRONT") {
    forward();
    Serial.println("ACK:FORWARD");
  } 
  else if (cmd == "B" || cmd == "BACKWARD" || cmd == "BACK") {
    backward();
    Serial.println("ACK:BACKWARD");
  } 
  else if (cmd == "L" || cmd == "LEFT") {
    turnLeft();
    Serial.println("ACK:LEFT");
  } 
  else if (cmd == "R" || cmd == "RIGHT") {
    turnRight();
    Serial.println("ACK:RIGHT");
  } 
  else if (cmd == "S" || cmd == "STOP") {
    stopMotors();
    Serial.println("ACK:STOP");
  }
  else if (cmd == "PING") {
    Serial.println("PONG");
  }
  else {
    Serial.print("WARN:UNKNOWN_CMD:");
    Serial.println(cmd);
  }
}

// =====================================
// SETUP
// =====================================
void setup() {
  // Communication with Raspberry Pi via Hardware Serial (USB)
  Serial.begin(115200);
  Serial.setTimeout(50);
  delay(500);

  // Motor pins
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Ultrasonic pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Flame sensor pins
  pinMode(FLAME_AO, INPUT);
  pinMode(FLAME_DO, INPUT);

  // Servo scanner initialization (fixed forward 90 degrees)
  scanner.setPeriodHertz(50);
  scanner.attach(SERVO_PIN, 500, 2400);
  scanner.write(90);
  delay(200);

  stopMotors();

  lastCommandTime = millis();
  Serial.println("SYSTEM:READY");
}

// =====================================
// MAIN LOOP
// =====================================
void loop() {
  unsigned long now = millis();

  // 1. FIRE SENSOR MONITORING & INSTANT EVENT REPORTING
  // When fire is first detected, immediately stop motors once and alert RPi.
  // It does NOT continuously force stop, ensuring commands from RPi are never overwritten.
  bool currentFlame = flameDetected();
  if (currentFlame != lastFlameState) {
    lastFlameState = currentFlame;
    if (currentFlame) {
      stopMotors();
      Serial.println("EVENT:FIRE_DETECTED");
    } else {
      Serial.println("EVENT:FIRE_CLEARED");
    }
  }

  // 2. RECEIVE COMMANDS FROM RASPBERRY PI
  // Commands from RPi (e.g. steering away from fire or stopping) are immediately executed
  while (Serial.available() > 0) {
    String incoming = Serial.readStringUntil('\n');
    processCommand(incoming);
  }

  // 3. FAILSAFE: Auto-stop if no movement refresh within safety window
  // (Prevents robot from driving infinitely if Raspberry Pi or network disconnects)
  if (currentMovement != "STOP" && (now - lastCommandTime > SAFETY_TIMEOUT_MS)) {
    stopMotors();
    Serial.println("EVENT:SAFETY_TIMEOUT_STOP");
  }

  // 4. PERIODIC TELEMETRY (Every 250ms: Distance & Fire Status)
  if (now - lastTelemetryTime >= 250) {
    lastTelemetryTime = now;
    float dist = getDistance();

    // Front obstacle auto-stop safety when moving forward
    if (currentMovement == "FORWARD" && dist > 0 && dist < OBSTACLE_DISTANCE) {
      stopMotors();
      Serial.println("EVENT:OBSTACLE_DETECTED");
    }

    Serial.print("TELEMETRY:{\"distance\":");
    Serial.print(dist, 1);
    Serial.print(",\"fire\":");
    Serial.print(currentFlame ? "true" : "false");
    Serial.print(",\"state\":\"");
    Serial.print(currentMovement);
    Serial.println("\"}");
  }

  delay(10);
}
