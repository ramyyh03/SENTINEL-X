// ============================================================================
//  SENTINEL-X — MODE DIAGNOSTIC MATÉRIEL (sans WiFi)
//  But : brancher les composants un par un et voir EN DIRECT dans le terminal
//  s'ils sont détectés. Pas de WiFi/MQTT -> pas de pic de courant -> pas de
//  crash : on isole proprement chaque capteur et son câblage.
//
//  Flasher :   make.bat flash-diag     (ou : pio run -d firmware -e esp32dev-diag -t upload)
//  Observer :  make.bat monitor-esp32
// ============================================================================
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

const int PIN_DHT        = 4;    // DHT22
const int PIN_PIR        = 27;   // PIR
const int PIN_MQ2        = 34;   // MQ-2 (sortie analogique AO)
const int PIN_LED_VERT   = 26;   // LED verte
const int PIN_LED_ORANGE = 14;   // LED orange
const int PIN_LED_ROUGE  = 13;   // LED rouge

DHT dht(PIN_DHT, DHT22);
Adafruit_SSD1306 display(128, 64, &Wire, -1);
bool oledInit = false;

void setup() {
  Serial.begin(115200);
  delay(400);
  Wire.begin(21, 22);
  dht.begin();
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_LED_VERT, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  analogReadResolution(12);
  oledInit = display.begin(SSD1306_SWITCHCAPVCC, 0x3C)
          || display.begin(SSD1306_SWITCHCAPVCC, 0x3D);

  Serial.println();
  Serial.println("=====================================================");
  Serial.println("   SENTINEL-X - DIAGNOSTIC MATERIEL (sans WiFi)");
  Serial.println("   Branche un composant a la fois, regarde ci-dessous.");
  Serial.println("=====================================================");
}

void loop() {
  // --- OLED : présence sur le bus I2C (0x3C) ---
  Wire.beginTransmission(0x3C);
  bool oledVu = (Wire.endTransmission() == 0);

  // --- DHT22 : lecture (NaN = non branché / mauvais câblage) ---
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  bool dhtOk = !isnan(t) && !isnan(h);

  // --- MQ-2 : valeur ADC brute (change si branché ; ~0 ou ~4095 = suspect) ---
  int gaz = analogRead(PIN_MQ2);
  bool mq2Plausible = (gaz > 10 && gaz < 4085);

  // --- PIR : état numérique ---
  int pir = digitalRead(PIN_PIR);

  Serial.println("-----------------------------------------------------");
  Serial.printf("OLED  (I2C 0x3C) : %s\n", oledVu ? "DETECTE" : "absent");
  if (dhtOk)
    Serial.printf("DHT22 (temp/hum) : DETECTE   T=%.1f C   H=%.1f %%\n", t, h);
  else
    Serial.println("DHT22 (temp/hum) : absent (lecture NaN - verifie VCC/GND/DATA=GPIO4)");
  Serial.printf("MQ-2  (gaz AO)   : valeur=%4d  %s\n",
                gaz, mq2Plausible ? "(branche, plausible)" : "(verifie le branchement AO->GPIO34)");
  Serial.printf("PIR   (presence) : %s\n", pir ? "MOUVEMENT detecte" : "rien");

  // --- Test LEDs : chacune s'allume 300 ms -> tu vois laquelle marche ---
  Serial.println("LEDs : verte -> orange -> rouge (300ms chacune)");
  digitalWrite(PIN_LED_VERT, HIGH);   delay(300); digitalWrite(PIN_LED_VERT, LOW);
  digitalWrite(PIN_LED_ORANGE, HIGH); delay(300); digitalWrite(PIN_LED_ORANGE, LOW);
  digitalWrite(PIN_LED_ROUGE, HIGH);  delay(300); digitalWrite(PIN_LED_ROUGE, LOW);

  // --- Récap sur l'OLED si présente ---
  if (oledInit && oledVu) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);  display.println("DIAGNOSTIC");
    display.setCursor(0, 16); display.printf("DHT:%s  MQ2:%d", dhtOk ? "OK" : "--", gaz);
    display.setCursor(0, 32); display.printf("PIR:%s", pir ? "OUI" : "non");
    display.setCursor(0, 48); display.println("sans WiFi");
    display.display();
  }

  delay(700);
}
