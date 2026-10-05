// ============================================================================
//  SENTINEL-X — Firmware ESP32
//  DHT22 + écran OLED (local)  +  WiFi + publication MQTT (vers la Brique 3)
//
//  Configuration SANS toucher au code : au 1er démarrage, l'ESP32 ouvre un
//  réseau WiFi « SENTINEL-X-SETUP ». On s'y connecte (téléphone/PC), une page
//  web s'ouvre, on saisit : SSID, mot de passe WiFi, IP du PC-broker.
//  Tout est mémorisé dans la flash → plus rien à ressaisir ensuite.
//
//  Aucun identifiant n'est écrit dans le code ni poussé sur GitHub.
// ============================================================================
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <WiFi.h>
#include <WiFiManager.h>      // tzapu/WiFiManager — portail de config WiFi
#include <PubSubClient.h>     // knolleary — client MQTT
#include <ArduinoJson.h>      // bblanchon — sérialisation JSON (v7)
#include <Preferences.h>      // stockage persistant (IP du broker) en flash NVS
#include <time.h>

// --- Broches ---
const int PIN_DHT = 4;  // DHT22 sur GPIO 4

// --- Constantes réseau / MQTT ---
const char* AP_NAME        = "SENTINEL-X-SETUP";  // réseau WiFi de configuration
const char* AP_PASSWORD    = "sentinel";          // mot de passe du portail (8 car. min.)
const char* MQTT_TOPIC     = "sentinel/sensors";  // topic attendu par la Brique 3
const int   MQTT_PORT      = 1883;                 // dev (clair). Prod = 8883 (TLS)
const int   PORTAL_TIMEOUT = 180;                  // s : ferme le portail si inactif

// --- Cadence de lecture ---
const unsigned long PERIODE_MS = 2000;  // DHT22 : 1 lecture / 2 s maximum

// --- Objets matériels / réseau ---
Adafruit_SSD1306 display(128, 64, &Wire, -1);
DHT dht(PIN_DHT, DHT22);
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
Preferences  prefs;

// --- État ---
char  brokerIp[40] = "";       // IP du PC-broker (saisie au portail, stockée en flash)
bool  saveBroker   = false;    // vrai si l'utilisateur vient de (re)configurer
float temperature  = NAN;
float humidite     = NAN;
unsigned long derniereLecture = 0;

// ---------------------------------------------------------------------------
//  OLED : petit utilitaire d'affichage (jusqu'à 3 lignes)
// ---------------------------------------------------------------------------
void oledLignes(const char* l1, const char* l2 = "", const char* l3 = "") {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);  display.println("SENTINEL-X");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);
  display.setCursor(0, 16); display.println(l1);
  display.setCursor(0, 30); display.println(l2);
  display.setCursor(0, 44); display.println(l3);
  display.display();
}

// ---------------------------------------------------------------------------
//  WiFiManager : connexion via les identifiants sauvegardés, sinon portail
// ---------------------------------------------------------------------------
void saveConfigCallback() { saveBroker = true; }

void configurerWiFi() {
  // On recharge l'IP broker déjà mémorisée (vide au tout premier démarrage)
  prefs.begin("sentinel", true);                 // lecture seule
  prefs.getString("broker", "").toCharArray(brokerIp, sizeof(brokerIp));
  prefs.end();

  WiFiManager wm;
  wm.setConfigPortalTimeout(PORTAL_TIMEOUT);
  wm.setSaveConfigCallback(saveConfigCallback);

  // Champ personnalisé « IP du PC-broker » ajouté au formulaire web
  WiFiManagerParameter champBroker("broker", "IP du PC (broker MQTT)", brokerIp, 40);
  wm.addParameter(&champBroker);

  oledLignes("Config WiFi :", "Reseau WiFi :", AP_NAME);
  Serial.printf("Portail de config → réseau WiFi « %s »\n", AP_NAME);

  // Tente les identifiants mémorisés ; sinon ouvre le portail captif
  if (!wm.autoConnect(AP_NAME, AP_PASSWORD)) {
    Serial.println("Echec config WiFi → redémarrage");
    oledLignes("Echec WiFi", "Redemarrage...");
    delay(1500);
    ESP.restart();
  }

  // Récupère l'IP saisie et la persiste si l'utilisateur a (re)configuré
  strncpy(brokerIp, champBroker.getValue(), sizeof(brokerIp) - 1);
  brokerIp[sizeof(brokerIp) - 1] = '\0';
  if (saveBroker) {
    prefs.begin("sentinel", false);              // écriture
    prefs.putString("broker", brokerIp);
    prefs.end();
  }

  Serial.printf("WiFi OK — IP locale %s | broker MQTT %s:%d\n",
                WiFi.localIP().toString().c_str(), brokerIp, MQTT_PORT);
  mqtt.setServer(brokerIp, MQTT_PORT);
}

// ---------------------------------------------------------------------------
//  Horodatage ISO 8601 (UTC) via NTP — format attendu par la Brique 3
// ---------------------------------------------------------------------------
void configurerHeure() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");  // UTC
}

String horodatageISO() {
  time_t maintenant = time(nullptr);
  if (maintenant < 100000) return "1970-01-01T00:00:00Z";  // NTP pas encore synchro
  struct tm t;
  gmtime_r(&maintenant, &t);
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &t);
  return String(buf);
}

// ---------------------------------------------------------------------------
//  MQTT : (re)connexion non bloquante + publication d'une mesure en JSON
// ---------------------------------------------------------------------------
void assurerMQTT() {
  if (strlen(brokerIp) == 0 || mqtt.connected()) return;
  String clientId = "sentinel-esp32-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  mqtt.connect(clientId.c_str());  // auth MQTT (user/pwd) à ajouter en prod
}

void publierMesure() {
  // Format EXACT attendu par le client Python (Brique 3) :
  // {temp, humidity, gas, presence, timestamp}
  JsonDocument doc;
  doc["temp"]      = temperature;
  doc["humidity"]  = humidite;
  doc["gas"]       = 0;    // TODO : capteur MQ-2 absent → placeholder (0) pour l'instant
  doc["presence"]  = 0;    // TODO : capteur PIR  absent → placeholder (0) pour l'instant
  doc["timestamp"] = horodatageISO();

  char payload[192];
  size_t n = serializeJson(doc, payload);
  if (mqtt.publish(MQTT_TOPIC, payload, n))
    Serial.printf("MQTT → %s : %s\n", MQTT_TOPIC, payload);
  else
    Serial.println("MQTT : échec de publication");
}

// ---------------------------------------------------------------------------
//  Lecture capteur + affichages
// ---------------------------------------------------------------------------
void lireCapteurs() {
  temperature = dht.readTemperature();
  humidite    = dht.readHumidity();
}

void afficherSerie() {
  if (isnan(temperature) || isnan(humidite))
    Serial.println("DHT22 : lecture impossible (verifier cablage)");
  else
    Serial.printf("T=%.1f C  H=%.1f %%\n", temperature, humidite);
}

void afficherOLED() {
  // Ligne d'état réseau : connecté au broker ou non
  const char* etat = mqtt.connected() ? "MQTT: OK" : "MQTT: ...";
  char lT[16], lH[16];
  if (isnan(temperature)) snprintf(lT, sizeof(lT), "T: --");
  else                    snprintf(lT, sizeof(lT), "T: %.1f C", temperature);
  if (isnan(humidite))    snprintf(lH, sizeof(lH), "H: --");
  else                    snprintf(lH, sizeof(lH), "H: %.1f %%", humidite);
  oledLignes(lT, lH, etat);
}

// ---------------------------------------------------------------------------
//  setup / loop
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);  // I²C : SDA=21, SCL=22

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED introuvable");
    while (true) delay(1000);
  }
  display.setTextColor(SSD1306_WHITE);

  dht.begin();
  configurerWiFi();    // connexion WiFi (portail si 1ʳᵉ fois)
  configurerHeure();   // NTP pour l'horodatage ISO
  Serial.println("Sentinel-X : OLED + DHT22 + MQTT prets");
}

void loop() {
  assurerMQTT();
  mqtt.loop();

  if (millis() - derniereLecture >= PERIODE_MS) {
    derniereLecture = millis();
    lireCapteurs();
    afficherSerie();
    afficherOLED();
    // On ne publie que des mesures valides, et seulement si MQTT est connecté
    if (!isnan(temperature) && !isnan(humidite) && mqtt.connected())
      publierMesure();
  }
}
