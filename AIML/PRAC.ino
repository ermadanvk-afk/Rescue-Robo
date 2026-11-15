#include <Wire.h>
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
// MPU6050
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
// BEHAVIOUR SETTINGS (tune these)
// =====================================

// Front distance below this (cm) = obstacle
const float OBSTACLE_DISTANCE = 30;

// A side must be at least this clear (cm) to drive that way
const float SIDE_CLEAR_DISTANCE = 35;

// Value used when the sensor gets NO echo = nothing in range = open space
const float OPEN_DISTANCE = 400;

// If we lose the echo right after a reading closer than this (cm),
// the object is probably too close for the sensor to see -> treat as obstacle
const float NEAR_BLIND_DISTANCE = 40;

// Turn sizes (degrees, measured with the MPU6050) and safety timeouts
const float SIDE_TURN_ANGLE = 75;
const float TURN_AROUND_ANGLE = 170;
const unsigned long SIDE_TURN_TIMEOUT = 1500;
const unsigned long TURN_AROUND_TIMEOUT = 3000;

// Last front reading, used for the "too close to see" check
float lastFrontDistance = OPEN_DISTANCE;

// =====================================
// MPU FUNCTIONS
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

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MPU_ADDR, 14) != 14) {
    return false;
  }

  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();

  Wire.read();
  Wire.read();

  int16_t gx = (Wire.read() << 8) | Wire.read();
  int16_t gy = (Wire.read() << 8) | Wire.read();
  int16_t gz = (Wire.read() << 8) | Wire.read();

  unsigned long now = micros();

  if (lastMPUTime != 0) {

    float dt = (now - lastMPUTime) / 1000000.0;

    float gyroZ = gz / 131.0 - gyroZOffset;

    yaw += gyroZ * dt;
  }

  lastMPUTime = now;

  return true;
}

// =====================================
// MPU CALIBRATION
// =====================================

void calibrateMPU() {

  Serial.println("Calibrating MPU6050...");
  Serial.println("Keep robot completely still.");

  long total = 0;
  const int samples = 1000;
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

  Serial.print("Gyro Z offset: ");
  Serial.println(gyroZOffset);

  Serial.println("Calibration complete.");
}

// =====================================
// FLAME SENSOR
// =====================================

bool flameDetected() {
  return digitalRead(FLAME_DO) == FLAME_ACTIVE;
}

void printFlameData() {

  int analogValue = analogRead(FLAME_AO);
  int digitalValue = digitalRead(FLAME_DO);

  Serial.print("Flame AO: ");
  Serial.print(analogValue);

  Serial.print(" | Flame DO: ");
  Serial.print(digitalValue);

  Serial.print(" | Status: ");

  Serial.println(
    digitalValue == FLAME_ACTIVE
    ? "FLAME DETECTED"
    : "NO FLAME"
  );
}

// =====================================
// ULTRASONIC SENSOR
// =====================================

// Returns distance in cm, or -1 if no echo came back
float getDistance() {

  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(5);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration =
    pulseIn(ECHO_PIN, HIGH, 30000);

  if (duration == 0) {
    return -1;
  }

  return duration * 0.0343 / 2;
}

// Takes several readings and returns the CLOSEST valid one (safer).
// If no reading got an echo, returns OPEN_DISTANCE (nothing in range),
// so the robot keeps moving instead of stopping.
float getStableDistance(int samples) {

  float closest = -1;

  for (int i = 0; i < samples; i++) {

    float d = getDistance();

    if (d > 0 && (closest < 0 || d < closest)) {
      closest = d;
    }

    delay(30);
  }

  if (closest < 0) {
    return OPEN_DISTANCE;
  }

  return closest;
}

// =====================================
// MOTOR CONTROL
// =====================================

void enableMotors() {

  digitalWrite(ENA, HIGH);
  digitalWrite(ENB, HIGH);
}

void forward() {

  enableMotors();

  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);

  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void backward() {

  enableMotors();

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);

  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void turnLeft() {

  enableMotors();

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);

  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void turnRight() {

  enableMotors();

  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);

  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void stopMotors() {

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);

  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

// =====================================
// CONTROLLED MOVEMENT DELAY
// =====================================

bool controlledDelay(unsigned long duration) {

  unsigned long start = millis();

  while (millis() - start < duration) {

    readMPU();

    if (flameDetected()) {

      stopMotors();

      Serial.println("FLAME DETECTED - STOPPING");

      return false;
    }

    delay(10);
  }

  return true;
}

// =====================================
// TURN BY ANGLE (uses the MPU6050 yaw)
// =====================================
// Turns until the robot has rotated targetDeg degrees, so the turn
// size doesn't depend on battery level or floor grip.
// Falls back to a timeout if the gyro isn't responding.

bool turnByAngle(bool left, float targetDeg, unsigned long timeoutMs) {

  readMPU();

  float startYaw = yaw;
  unsigned long start = millis();

  if (left) {
    turnLeft();
  }
  else {
    turnRight();
  }

  while (fabs(yaw - startYaw) < targetDeg) {

    if (millis() - start > timeoutMs) {
      break;
    }

    if (flameDetected()) {

      stopMotors();

      Serial.println("FLAME DETECTED - STOPPING");

      return false;
    }

    readMPU();

    delay(5);
  }

  stopMotors();

  return true;
}

// =====================================
// SERVO SCANNING
// =====================================

float scanAt(int angle) {

  scanner.write(angle);
  delay(400);

  float distance = getStableDistance(3);

  Serial.print("Angle ");
  Serial.print(angle);
  Serial.print(" degrees: ");

  if (distance >= OPEN_DISTANCE) {
    Serial.println("No echo (open space)");
  }
  else {
    Serial.print(distance);
    Serial.println(" cm");
  }

  return distance;
}

// =====================================
// SETUP
// =====================================

void setup() {

  Serial.begin(115200);

  // Motor pins
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);

  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Ultrasonic
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Flame sensor
  pinMode(FLAME_AO, INPUT);
  pinMode(FLAME_DO, INPUT);

  // I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // MPU6050 initialization
  writeMPU(0x6B, 0x00);
  writeMPU(0x1B, 0x00);
  writeMPU(0x1C, 0x00);

  delay(100);

  Wire.beginTransmission(MPU_ADDR);

  if (Wire.endTransmission() == 0) {
    Serial.println("MPU6050 connected.");
  }
  else {
    Serial.println("ERROR: MPU6050 not detected!");
  }

  // Servo
  scanner.setPeriodHertz(50);
  scanner.attach(SERVO_PIN, 500, 2400);

  scanner.write(90);
  delay(300);

  stopMotors();

  calibrateMPU();

  Serial.println("Robot system ready.");
}

// =====================================
// MAIN LOOP
// =====================================

void loop() {

  // 1. Update MPU
  readMPU();

  Serial.print("\nYaw: ");
  Serial.print(yaw, 2);
  Serial.println(" degrees");

  // 2. Check flame sensor
  printFlameData();

  if (flameDetected()) {

    stopMotors();
    scanner.write(90);

    Serial.println("FLAME DETECTED - ROBOT STOPPED");

    delay(300);
    return;
  }

  // 3. Check front distance
  //    (servo is already at 90 degrees, so no extra wait here)
  float frontDistance = getStableDistance(2);

  bool noEcho = (frontDistance >= OPEN_DISTANCE);

  // No echo right after a close reading = object is probably too
  // close for the sensor to see, so treat it as an obstacle.
  bool blindObstacle = noEcho && (lastFrontDistance < NEAR_BLIND_DISTANCE);

  lastFrontDistance = frontDistance;

  Serial.print("Front distance: ");

  if (noEcho) {

    if (blindObstacle) {
      Serial.println("No echo, but was close a moment ago - TREATING AS OBSTACLE");
    }
    else {
      Serial.println("No echo - open space");
    }
  }
  else {
    Serial.print(frontDistance);
    Serial.println(" cm");
  }

  // 4. Path clear (including no echo) - keep moving forward
  if (!blindObstacle && frontDistance > OBSTACLE_DISTANCE) {

    Serial.println("PATH CLEAR - MOVING FORWARD");

    forward();

    return;
  }

  // 5. Obstacle detected - stop and back off a little to make room
  Serial.println("OBSTACLE DETECTED");

  stopMotors();
  delay(200);

  backward();

  if (!controlledDelay(250)) {
    return;
  }

  stopMotors();
  delay(150);

  // 6. Scan left and right
  //    (if left/right are mirrored on your robot, swap 150 and 30)
  float leftDistance = scanAt(150);
  float rightDistance = scanAt(30);

  scanner.write(90);
  delay(300);

  if (flameDetected()) {

    stopMotors();
    return;
  }

  // 7. Pick a clear side, or go back and turn around.
  //    The robot never drives forward into the obstacle from here.
  bool leftClear = leftDistance > SIDE_CLEAR_DISTANCE;
  bool rightClear = rightDistance > SIDE_CLEAR_DISTANCE;

  if (leftClear || rightClear) {

    bool goLeft = (leftDistance >= rightDistance);

    if (goLeft) {
      Serial.println("LEFT IS CLEARER - TURNING LEFT");
    }
    else {
      Serial.println("RIGHT IS CLEARER - TURNING RIGHT");
    }

    if (!turnByAngle(goLeft, SIDE_TURN_ANGLE, SIDE_TURN_TIMEOUT)) {
      return;
    }
  }
  else {

    Serial.println("BOTH SIDES BLOCKED - GOING BACK AND TURNING AROUND");

    backward();

    if (!controlledDelay(300)) {
      return;
    }

    stopMotors();
    delay(150);

    if (!turnByAngle(true, TURN_AROUND_ANGLE, TURN_AROUND_TIMEOUT)) {
      return;
    }
  }

  stopMotors();

  delay(200);

  // Fresh start: next loop re-checks the front before moving
  lastFrontDistance = OPEN_DISTANCE;
}