#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

// --- Broches ---
const int PIN_DHT = 4;  // D4

// --- Objets ---
Adafruit_SSD1306 display(128, 64, &Wire, -1);
DHT dht(PIN_DHT, DHT22);

// --- Mesures ---
float temperature = NAN;
float humidite = NAN;

unsigned long derniereLecture = 0;
const unsigned long PERIODE_MS = 2000;  // le DHT22 ne supporte pas plus d'une lecture toutes les 2 s

void lireCapteurs() {
  temperature = dht.readTemperature();
  humidite = dht.readHumidity();
}

void afficherSerie() {
  if (isnan(temperature) || isnan(humidite)) {
    Serial.println("DHT22 : lecture impossible (verifier cablage)");
  } else {
    Serial.printf("T=%.1f C  H=%.1f %%\n", temperature, humidite);
  }
}

void afficherOLED() {
  display.clearDisplay();

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("SENTINEL-X");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

  display.setTextSize(2);
  display.setCursor(0, 18);
  if (isnan(temperature)) display.println("T: --");
  else display.printf("T:%.1fC\n", temperature);

  display.setCursor(0, 42);
  if (isnan(humidite)) display.println("H: --");
  else display.printf("H:%.1f%%\n", humidite);

  display.display();
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED introuvable");
    while (true) delay(1000);
  }
  display.setTextColor(SSD1306_WHITE);

  dht.begin();
  Serial.println("Sentinel-X : OLED + DHT22 prets");
}

void loop() {
  if (millis() - derniereLecture >= PERIODE_MS) {
    derniereLecture = millis();
    lireCapteurs();
    afficherSerie();
    afficherOLED();
  }
}