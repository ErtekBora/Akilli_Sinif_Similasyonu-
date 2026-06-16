#include <DHT.h>

#define PIR_PIN 12
#define LDR_PIN 34
#define CO2_POT_PIN 35
#define DHT_PIN 15
#define LED_PIN 2
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);

const unsigned long BEKLEME_SURESI_MS = 15000;
const unsigned long CAPTURE_INTERVAL_MS = 500;
const unsigned long SERIAL_INTERVAL_MS = 500;

const float DHT22_TEMP_TOLERANCE_C = 0.5;
const float DHT22_HUMIDITY_TOLERANCE_PERCENT = 2.0;
const float AC_SETPOINT_C = 22.0;
const int TEMP_WINDOW = 5;

unsigned long sonHareketZamani = 0;
unsigned long sonCaptureZamani = 0;
unsigned long sonSerialZamani = 0;

bool sinifDolu = false;
bool hvacAktif = false;

float sicaklikOrnekleri[TEMP_WINDOW];
int sicaklikIndex = 0;
int sicaklikSayisi = 0;

struct SensorFrame {
  int pirDurum;
  int ldrDegeri;
  int co2PotDegeri;
  int luks;
  int co2;
  int ledParlaklik;
  float sicaklikHam;
  float sicaklikFiltreli;
  float nem;
};

SensorFrame frame = {0, 0, 0, 0, 400, 0, 24.5, 24.5, 45.0};

float readAndFilterTemperature() {
  float okuma = dht.readTemperature();
  if (isnan(okuma)) {
    okuma = frame.sicaklikFiltreli;
  }

  frame.sicaklikHam = okuma;
  sicaklikOrnekleri[sicaklikIndex] = okuma;
  sicaklikIndex = (sicaklikIndex + 1) % TEMP_WINDOW;
  if (sicaklikSayisi < TEMP_WINDOW) {
    sicaklikSayisi++;
  }

  float toplam = 0.0;
  for (int i = 0; i < sicaklikSayisi; i++) {
    toplam += sicaklikOrnekleri[i];
  }

  frame.sicaklikFiltreli = toplam / sicaklikSayisi;
  return frame.sicaklikFiltreli;
}

float readHumidityWithFallback() {
  float okuma = dht.readHumidity();
  if (isnan(okuma)) {
    return frame.nem;
  }
  return okuma;
}

void updateOccupancy(unsigned long simdi) {
  frame.pirDurum = digitalRead(PIR_PIN);

  if (frame.pirDurum == HIGH) {
    sonHareketZamani = simdi;
    sinifDolu = true;
  }

  if (sinifDolu && (simdi - sonHareketZamani >= BEKLEME_SURESI_MS)) {
    sinifDolu = false;
  }
}

int calculateLux(int ldrDegeri) {
  float voltaj = ldrDegeri / 4095.0 * 3.3;
  if (voltaj <= 0) voltaj = 0.001;
  if (voltaj >= 3.3) voltaj = 3.299;

  float direnc = 10000.0 * voltaj / (3.3 - voltaj);
  float gercekLuks = pow(250593.5 / direnc, 1.42857);
  return constrain(round(gercekLuks), 0, 100000);
}

int calculateLedPwm(int luks) {
  if (!sinifDolu || luks >= 500) {
    return 0;
  }

  int lineerPwm = map(luks, 0, 500, 255, 0);
  lineerPwm = constrain(lineerPwm, 0, 255);
  return (lineerPwm * lineerPwm) / 255;
}

void updateHvacDeadband() {
  if (!sinifDolu) {
    hvacAktif = false;
    return;
  }

  if (frame.sicaklikFiltreli >= AC_SETPOINT_C + DHT22_TEMP_TOLERANCE_C) {
    hvacAktif = true;
  } else if (frame.sicaklikFiltreli <= AC_SETPOINT_C - DHT22_TEMP_TOLERANCE_C) {
    hvacAktif = false;
  }
}

void captureSensors(unsigned long simdi) {
  if (simdi - sonCaptureZamani < CAPTURE_INTERVAL_MS) {
    return;
  }
  sonCaptureZamani = simdi;

  frame.ldrDegeri = analogRead(LDR_PIN);
  frame.co2PotDegeri = analogRead(CO2_POT_PIN);
  frame.sicaklikFiltreli = readAndFilterTemperature();
  frame.nem = readHumidityWithFallback();
  frame.luks = calculateLux(frame.ldrDegeri);
  frame.co2 = map(frame.co2PotDegeri, 0, 4095, 400, 2000);
  frame.ledParlaklik = calculateLedPwm(frame.luks);

  updateHvacDeadband();
  ledcWrite(LED_PIN, frame.ledParlaklik);
}

void printSensorReport(unsigned long simdi) {
  if (simdi - sonSerialZamani < SERIAL_INTERVAL_MS) {
    return;
  }
  sonSerialZamani = simdi;

  if (sinifDolu) {
    Serial.print("Hareket: VAR (");
    Serial.print((BEKLEME_SURESI_MS - (simdi - sonHareketZamani)) / 1000);
    Serial.print("s)");
  } else {
    Serial.print("Hareket Algilanmadi");
  }

  Serial.print(" | Lux: "); Serial.print(frame.luks);
  Serial.print(" | SicaklikHam: "); Serial.print(frame.sicaklikHam, 1); Serial.print("C");
  Serial.print(" | SicaklikFiltreli: "); Serial.print(frame.sicaklikFiltreli, 1); Serial.print("C");
  Serial.print(" | Tol: +/-"); Serial.print(DHT22_TEMP_TOLERANCE_C, 1); Serial.print("C");
  Serial.print(" | Nem: %"); Serial.print(frame.nem, 1);
  Serial.print(" (+/-"); Serial.print(DHT22_HUMIDITY_TOLERANCE_PERCENT, 1); Serial.print("%)");
  Serial.print(" | CO2: "); Serial.print(frame.co2); Serial.print(" PPM");
  Serial.print(" | HVAC: "); Serial.print(hvacAktif ? "AKTIF" : "PASIF");
  Serial.print(" | PWM: "); Serial.println(frame.ledParlaklik);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  dht.begin();

  for (int i = 0; i < TEMP_WINDOW; i++) {
    sicaklikOrnekleri[i] = frame.sicaklikFiltreli;
  }

  ledcAttach(LED_PIN, 5000, 8);

  Serial.println("--- SISTEM AKTIF: MODULER CAPTURE, DHT22 TOLERANS & MILLIS TIMER ---");
}

void loop() {
  unsigned long simdi = millis();
  updateOccupancy(simdi);
  captureSensors(simdi);
  printSensorReport(simdi);
}
