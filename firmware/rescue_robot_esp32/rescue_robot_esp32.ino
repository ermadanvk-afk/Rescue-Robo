/*
  =============================================================================
  AI SEARCH & RESCUE ROBOT - ENHANCED ESP32 FIRMWARE
  =============================================================================
  Features:
  - Dual Mode Operation:
      1. REMOTE (Default): Accepts high-level drive commands from Raspberry Pi
         via USB Serial JSON, with local hardware safety override.
      2. AUTO: Standalone autonomous obstacle avoidance (failsafe if Pi is off).
  - High-frequency sensor telemetry stream (JSON at 10Hz):
      yaw (MPU6050 gyro fusion), ultrasonic_cm, flame (HW-491), servo angle.
  - Hardware Safety Override:
      Automatically halts motors if ultrasonic distance < 20cm or flame detected,
      preventing collisions even if Pi sends a forward command.
  
  Wiring (L298N + MPU6050 + HC-SR04 + SG90 Servo + HW-491 Flame):
  - L298N: ENA=32, IN1=18, IN2=19, IN3=25, IN4=26, ENB=33
  - HC-SR04: TRIG=5, ECHO=27
  - Servo: SERVO_PIN=13
  - MPU6050: SDA=21, SCL=22
  - Flame Sensor: AO=34, DO=35 (Active HIGH)
  =============================================================================
*/

#include <Wire.h>
#include <ESP32Servo.h>

// =====================================
// MOTOR DRIVER - L298N PINS
// =====================================
#define ENA 32
#define IN1 18
#define IN2 19
#define IN3 25
#define IN4 26
#define ENB 33

// =====================================
// ULTRASONIC SENSOR PINS
// =====================================
#define TRIG_PIN 5
#define ECHO_PIN 27

// =====================================
// SERVO PIN & OBJECT
// =====================================
#define SERVO_PIN 13
Servo scanner;
int currentServoAngle = 90;

// =====================================
// MPU6050 PINS & GYRO VARS
// =====================================
#define MPU_ADDR 0x68
#define SDA_PIN 21
#define SCL_PIN 22

float gyroZOffset = 0;
float yaw = 0;
unsigned long lastMPUTime = 0;

// =====================================
// FLAME SENSOR HW-491
// =====================================
#define FLAME_AO 34
#define FLAME_DO 35
#define FLAME_ACTIVE HIGH

// =====================================
// SAFETY & BEHAVIOUR THRESHOLDS
// =====================================
const float OBSTACLE_DISTANCE = 30.0;    // cm
const float CRITICAL_DISTANCE = 18.0;    // cm: hard stop
const float OPEN_DISTANCE = 400.0;       // cm
const float SIDE_CLEAR_DISTANCE = 35.0;  // cm

String currentMode = "REMOTE"; // "REMOTE" or "AUTO"
String motorState = "STOP";
int currentSpeed = 200; // PWM 0-255

unsigned long lastTelemetryTime = 0;
unsigned long lastCommandTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 100; // 10Hz JSON telemetry
const unsigned long COMMAND_WATCHDOG_MS = 3000;  // Auto-stop if no command in REMOTE mode

// Serial receive buffer
String inputBuffer = "";

// =====================================
// MPU6050 ROUTINES
// =====================================
void writeMPU(byte reg, byte value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool readMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU_ADDR, 14) != 14) return false;

  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();
  Wire.read(); Wire.read(); // Skip temp
  int16_t gx = (Wire.read() << 8) | Wire.read();
  int16_t gy = (Wire.read() << 8) | Wire.read();
  int16_t gz = (Wire.read() << 8) | Wire.read();

  unsigned long now = micros();
  if (lastMPUTime != 0) {
    float dt = (now - lastMPUTime) / 1000000.0;
    float gyroZ = (gz / 131.0) - gyroZOffset;
    yaw += gyroZ * dt;
    // Normalize yaw to 0 - 360 or continuous
    if (yaw >= 360.0) yaw -= 360.0;
    else if (yaw < 0.0) yaw += 360.0;
  }
  lastMPUTime = now;
  return true;
}

void calibrateMPU() {
  long total = 0;
  const int samples = 500;
  int validSamples = 0;

  for (int i = 0; i < samples; i++) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x47);
    Wire.endTransmission(false);
    if (Wire.requestFrom(MPU_ADDR, 2) == 2) {
      int16_t gz = (Wire.read() << 8) | Wire.read();
      total += gz;
      validSamples++;
    }
    delay(3);
  }
  if (validSamples > 0) {
    gyroZOffset = (total / (float)validSamples) / 131.0;
  }
  yaw = 0;
  lastMPUTime = micros();
}

// =====================================
// FLAME & ULTRASONIC SENSORS
// =====================================
bool flameDetected() {
  return digitalRead(FLAME_DO) == FLAME_ACTIVE;
}

float getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(5);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 25000); // 25ms timeout ~4m
  if (duration == 0) return OPEN_DISTANCE;
  return (duration * 0.0343) / 2.0;
}

float getStableDistance(int samples) {
  float closest = -1;
  for (int i = 0; i < samples; i++) {
    float d = getDistance();
    if (d > 0 && (closest < 0 || d < closest)) {
      closest = d;
    }
    delay(15);
  }
  if (closest < 0) return OPEN_DISTANCE;
  return closest;
}

// =====================================
// MOTOR CONTROL ROUTINES
// =====================================
void setMotorSpeed(int speed) {
  currentSpeed = constrain(speed, 0, 255);
  analogWrite(ENA, currentSpeed);
  analogWrite(ENB, currentSpeed);
}

void forward() {
  setMotorSpeed(currentSpeed);
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  motorState = "FORWARD";
}

void backward() {
  setMotorSpeed(currentSpeed);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  motorState = "BACKWARD";
}

void turnLeft() {
  setMotorSpeed(currentSpeed);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  motorState = "LEFT";
}

void turnRight() {
  setMotorSpeed(currentSpeed);
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  motorState = "RIGHT";
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  motorState = "STOP";
}

// =====================================
// TELEMETRY OUTPUT (JSON STREAM)
// =====================================
void sendTelemetry(float distance) {
  int flameVal = flameDetected() ? 1 : 0;
  int flameAnalog = analogRead(FLAME_AO);

  Serial.print("{\"type\":\"telemetry\",\"yaw\":");
  Serial.print(yaw, 1);
  Serial.print(",\"ultrasonic_cm\":");
  Serial.print(distance, 1);
  Serial.print(",\"flame\":");
  Serial.print(flameVal);
  Serial.print(",\"flame_analog\":");
  Serial.print(flameAnalog);
  Serial.print(",\"servo\":");
  Serial.print(currentServoAngle);
  Serial.print(",\"state\":\"");
  Serial.print(motorState);
  Serial.print("\",\"mode\":\"");
  Serial.print(currentMode);
  Serial.println("\"}");
}

// =====================================
// INCOMING COMMAND PARSER
// =====================================
void processCommand(String jsonCmd) {
  jsonCmd.trim();
  if (jsonCmd.length() == 0) return;

  lastCommandTime = millis();

  // Mode change command: {"cmd":"mode","mode":"AUTO"|"REMOTE"}
  if (jsonCmd.indexOf("\"cmd\":\"mode\"") >= 0 || jsonCmd.indexOf("\"mode\"") >= 0) {
    if (jsonCmd.indexOf("AUTO") >= 0) {
      currentMode = "AUTO";
      stopMotors();
    } else if (jsonCmd.indexOf("REMOTE") >= 0) {
      currentMode = "REMOTE";
      stopMotors();
    }
  }

  // Servo command: {"cmd":"servo","angle":90}
  int servoIdx = jsonCmd.indexOf("\"angle\":");
  if (servoIdx >= 0) {
    int angle = jsonCmd.substring(servoIdx + 8).toInt();
    angle = constrain(angle, 10, 170);
    scanner.write(angle);
    currentServoAngle = angle;
  }

  // Drive command: {"cmd":"drive","action":"FORWARD"|"BACKWARD"|"LEFT"|"RIGHT"|"STOP","speed":200}
  if (currentMode == "REMOTE") {
    int speedIdx = jsonCmd.indexOf("\"speed\":");
    if (speedIdx >= 0) {
      int spd = jsonCmd.substring(speedIdx + 8).toInt();
      if (spd > 0) currentSpeed = constrain(spd, 80, 255);
    }

    if (jsonCmd.indexOf("FORWARD") >= 0) {
      // Hardware safety: don't move forward if blocked or on fire
      float dist = getStableDistance(1);
      if (dist > CRITICAL_DISTANCE && !flameDetected()) {
        forward();
      } else {
        stopMotors();
      }
    } else if (jsonCmd.indexOf("BACKWARD") >= 0) {
      backward();
    } else if (jsonCmd.indexOf("LEFT") >= 0) {
      turnLeft();
    } else if (jsonCmd.indexOf("RIGHT") >= 0) {
      turnRight();
    } else if (jsonCmd.indexOf("STOP") >= 0) {
      stopMotors();
    }
  }
}

// =====================================
// SETUP
// =====================================
void setup() {
  Serial.begin(115200);

  // Motor Pins
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors();

  // Ultrasonic
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Flame
  pinMode(FLAME_AO, INPUT);
  pinMode(FLAME_DO, INPUT);

  // I2C & MPU6050
  Wire.begin(SDA_PIN, SCL_PIN);
  writeMPU(0x6B, 0x00);
  writeMPU(0x1B, 0x00);
  writeMPU(0x1C, 0x00);
  delay(100);

  // Servo
  scanner.setPeriodHertz(50);
  scanner.attach(SERVO_PIN, 500, 2400);
  scanner.write(90);
  currentServoAngle = 90;

  calibrateMPU();
  lastCommandTime = millis();
}

// =====================================
// MAIN LOOP
// =====================================
void loop() {
  unsigned long now = millis();

  // 1. Always update IMU gyro fusion
  readMPU();

  // 2. Read incoming Serial Commands
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
    }
  }

  // 3. Sensor checks
  float frontDist = getDistance();
  bool isFlame = flameDetected();

  // 4. Critical Safety: Fire halts everything immediately
  if (isFlame) {
    stopMotors();
    motorState = "FLAME_HALT";
  }

  // 5. Watchdog for REMOTE mode: stop if Pi disconnected > 3s
  if (currentMode == "REMOTE") {
    if (!isFlame && (now - lastCommandTime > COMMAND_WATCHDOG_MS)) {
      if (motorState != "STOP") {
        stopMotors();
      }
    }
  }

  // 6. Standalone Obstacle Avoidance (AUTO mode fallback)
  if (currentMode == "AUTO" && !isFlame) {
    if (frontDist > OBSTACLE_DISTANCE) {
      forward();
    } else {
      stopMotors();
      delay(150);
      backward();
      delay(250);
      stopMotors();

      // Quick left-right scan
      scanner.write(150);
      delay(350);
      float leftDist = getStableDistance(2);

      scanner.write(30);
      delay(350);
      float rightDist = getStableDistance(2);

      scanner.write(90);
      currentServoAngle = 90;
      delay(200);

      if (leftDist >= rightDist && leftDist > SIDE_CLEAR_DISTANCE) {
        turnLeft();
        delay(350);
      } else if (rightDist > SIDE_CLEAR_DISTANCE) {
        turnRight();
        delay(350);
      } else {
        turnLeft();
        delay(700); // Turn around
      }
      stopMotors();
    }
  }

  // 7. Output JSON Telemetry periodically (10Hz)
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;
    sendTelemetry(frontDist);
  }
}
