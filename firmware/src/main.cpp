// ============================================================================
//  SENTINEL-X — Firmware ESP32
//  DHT22 + écran OLED (local)  +  WiFi + publication MQTT (vers la Brique 3)
//
//  Configuration SANS toucher au code : au 1er démarrage, l'ESP32 ouvre un
//  réseau WiFi « SENTINEL-X-SETUP ». On s'y connecte (téléphone/PC), une page
//  web s'ouvre, on saisit : SSID, mot de passe WiFi, IP du PC-broker,
//  identifiant et mot de passe MQTT.
//  Tout est mémorisé dans la flash → plus rien à ressaisir ensuite.
//
//  Sécurité : la liaison MQTT est chiffrée (TLS, port 8883) et le broker est
//  authentifié grâce au certificat de la CA interne (include/ca_cert.h, public).
//  Aucun identifiant n'est écrit dans le code ni poussé sur GitHub : le mot de
//  passe du portail est tiré au hasard sur chaque carte et affiché sur l'OLED.
// ============================================================================
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <WiFi.h>
#include <WiFiClientSecure.h> // client TCP chiffré (TLS)
#include <WiFiManager.h>      // tzapu/WiFiManager — portail de config WiFi
#include <PubSubClient.h>     // knolleary — client MQTT
#include <ArduinoJson.h>      // bblanchon — sérialisation JSON (v7)
#include <Preferences.h>      // stockage persistant (IP du broker) en flash NVS
#include <time.h>
#include "ca_cert.h"          // certificat PUBLIC de la CA interne (CA_CERT)

// --- Broches ---
const int PIN_DHT = 4;   // DHT22      sur GPIO 4  (température + humidité)
const int PIN_PIR = 27;  // PIR HC-SR501 sur GPIO 27 (présence, sortie numérique)
const int PIN_MQ2 = 34;  // MQ-2       sur GPIO 34 (gaz, entrée analogique ADC1)

// --- Constantes réseau / MQTT ---
const char* AP_NAME        = "SENTINEL-X-SETUP";  // réseau WiFi de configuration
const char* MQTT_TOPIC     = "sentinel/sensors";  // topic attendu par la Brique 3
const int   MQTT_PORT      = 8883;                 // MQTTS (TLS) — plus de port en clair
const int   PORTAL_TIMEOUT = 180;                  // s : ferme le portail si inactif

// --- Cadence de lecture ---
const unsigned long PERIODE_MS = 2000;  // DHT22 : 1 lecture / 2 s maximum
const unsigned long MQTT_RETRY_MS = 5000;  // délai entre deux tentatives de connexion MQTT

// --- Objets matériels / réseau ---
Adafruit_SSD1306 display(128, 64, &Wire, -1);
DHT dht(PIN_DHT, DHT22);
WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);
Preferences  prefs;

// --- État ---
char  brokerIp[40] = "";       // IP du PC-broker (saisie au portail, stockée en flash)
char  mqttUser[33] = "";       // identifiant MQTT (saisi au portail, stocké en flash)
char  mqttPass[65] = "";       // mot de passe MQTT (saisi au portail, stocké en flash)
char  apPassword[9] = "";      // mot de passe du portail : aléatoire, propre à chaque carte
bool  saveBroker   = false;    // vrai si l'utilisateur vient de (re)configurer
unsigned long derniereTentativeMQTT = 0;
float temperature  = NAN;
float humidite     = NAN;
int   gaz          = 0;      // valeur brute ADC MQ-2 (0..4095) — voir README pour la calibration ppm
bool  presence     = false;  // PIR : true = mouvement détecté
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

// Appelé seulement quand le portail s'ouvre : on affiche alors son mot de passe.
// Il faut donc avoir la carte sous les yeux pour pouvoir la reconfigurer.
void portailOuvertCallback(WiFiManager*) {
  char ligne[22];
  snprintf(ligne, sizeof(ligne), "MDP : %s", apPassword);
  oledLignes("Portail de config :", AP_NAME, ligne);
  Serial.printf("Portail de config → réseau WiFi « %s », mot de passe « %s »\n",
                AP_NAME, apPassword);
}

// Mot de passe du portail : tiré au hasard au 1er démarrage puis gardé en flash.
// (Alphabet sans caractères ambigus : pas de 0/O ni de 1/l/I.)
void chargerMotDePassePortail() {
  static const char ALPHABET[] = "abcdefghjkmnpqrstuvwxyz23456789";
  prefs.begin("sentinel", false);
  String stocke = prefs.getString("ap_pass", "");
  if (stocke.length() != sizeof(apPassword) - 1) {
    stocke = "";
    for (size_t i = 0; i < sizeof(apPassword) - 1; i++)
      stocke += ALPHABET[esp_random() % (sizeof(ALPHABET) - 1)];
    prefs.putString("ap_pass", stocke);
  }
  prefs.end();
  stocke.toCharArray(apPassword, sizeof(apPassword));
}

void configurerWiFi() {
  WiFi.mode(WIFI_STA);          // radio allumée : esp_random() fournit un vrai aléa
  chargerMotDePassePortail();

  // On recharge la config déjà mémorisée (vide au tout premier démarrage)
  prefs.begin("sentinel", true);                 // lecture seule
  prefs.getString("broker", "").toCharArray(brokerIp, sizeof(brokerIp));
  prefs.getString("mqtt_user", "").toCharArray(mqttUser, sizeof(mqttUser));
  prefs.getString("mqtt_pass", "").toCharArray(mqttPass, sizeof(mqttPass));
  prefs.end();

  WiFiManager wm;
  wm.setConfigPortalTimeout(PORTAL_TIMEOUT);
  wm.setSaveConfigCallback(saveConfigCallback);
  wm.setAPCallback(portailOuvertCallback);

  // Champs personnalisés ajoutés au formulaire web.
  // Le mot de passe MQTT n'est jamais pré-rempli : il ne ressort pas de la carte.
  WiFiManagerParameter champBroker("broker", "IP du PC (broker MQTT)", brokerIp, 39);
  WiFiManagerParameter champUser("mqtt_user", "Identifiant MQTT", mqttUser, 32);
  WiFiManagerParameter champPass("mqtt_pass", "Mot de passe MQTT (vide = inchange)", "", 64,
                                 "type=\"password\"");
  wm.addParameter(&champBroker);
  wm.addParameter(&champUser);
  wm.addParameter(&champPass);

  oledLignes("Connexion WiFi...");

  // Config MQTT incomplète (ex. carte flashée avec l'ancien firmware) → on force
  // le portail. Sinon : identifiants WiFi mémorisés, et portail seulement en échec.
  bool configIncomplete = strlen(brokerIp) == 0 || strlen(mqttUser) == 0 || strlen(mqttPass) == 0;
  bool connecte = configIncomplete ? wm.startConfigPortal(AP_NAME, apPassword)
                                   : wm.autoConnect(AP_NAME, apPassword);
  if (!connecte) {
    Serial.println("Echec config WiFi → redémarrage");
    oledLignes("Echec WiFi", "Redemarrage...");
    delay(1500);
    ESP.restart();
  }

  // Récupère les valeurs saisies et les persiste si l'utilisateur a (re)configuré
  if (saveBroker) {
    strncpy(brokerIp, champBroker.getValue(), sizeof(brokerIp) - 1);
    brokerIp[sizeof(brokerIp) - 1] = '\0';
    strncpy(mqttUser, champUser.getValue(), sizeof(mqttUser) - 1);
    mqttUser[sizeof(mqttUser) - 1] = '\0';
    if (strlen(champPass.getValue()) > 0) {      // vide = on garde l'ancien
      strncpy(mqttPass, champPass.getValue(), sizeof(mqttPass) - 1);
      mqttPass[sizeof(mqttPass) - 1] = '\0';
    }
    prefs.begin("sentinel", false);              // écriture
    prefs.putString("broker", brokerIp);
    prefs.putString("mqtt_user", mqttUser);
    prefs.putString("mqtt_pass", mqttPass);
    prefs.end();
  }

  Serial.printf("WiFi OK — IP locale %s | broker MQTTS %s:%d (utilisateur %s)\n",
                WiFi.localIP().toString().c_str(), brokerIp, MQTT_PORT, mqttUser);

  // TLS : l'ESP32 n'accepte que les brokers dont le certificat est signé par
  // notre CA ET émis pour l'adresse saisie au portail (sinon : connexion refusée).
  wifiClient.setCACert(CA_CERT);
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
  // Une tentative TLS ratée bloque quelques secondes : on espace les essais
  // pour ne pas figer les capteurs et l'écran.
  if (derniereTentativeMQTT != 0 && millis() - derniereTentativeMQTT < MQTT_RETRY_MS) return;
  derniereTentativeMQTT = millis();

  String clientId = "sentinel-esp32-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  if (mqtt.connect(clientId.c_str(), mqttUser, mqttPass)) {
    Serial.println("MQTTS connecte (TLS + authentification)");
    return;
  }
  // state : -2 = TCP/TLS impossible (certificat, IP, pare-feu) ; 4/5 = identifiants refusés
  char erreurTls[100] = "";
  wifiClient.lastError(erreurTls, sizeof(erreurTls));
  Serial.printf("MQTTS : echec (state=%d) %s\n", mqtt.state(), erreurTls);
}

void publierMesure() {
  // Format EXACT attendu par le client Python (Brique 3) :
  // {temp, humidity, gas, presence, timestamp}
  JsonDocument doc;
  doc["temp"]      = temperature;
  doc["humidity"]  = humidite;
  doc["gas"]       = gaz;              // MQ-2 : valeur brute ADC (0..4095)
  doc["presence"]  = presence ? 1 : 0; // PIR  : 1 = présence, 0 = rien
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
  gaz         = analogRead(PIN_MQ2);         // MQ-2 : valeur brute 0..4095 (12 bits)
  presence    = digitalRead(PIN_PIR) == HIGH; // PIR : HIGH = mouvement
}

void afficherSerie() {
  if (isnan(temperature) || isnan(humidite))
    Serial.printf("DHT22 : lecture KO | Gaz=%d  PIR=%d\n", gaz, presence);
  else
    Serial.printf("T=%.1f C  H=%.1f %%  Gaz=%d  PIR=%d\n",
                  temperature, humidite, gaz, presence);
}

void afficherOLED() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // En-tête : état WiFi (IP si connecté) + indicateur MQTT
  display.setCursor(0, 0);
  if (WiFi.status() == WL_CONNECTED) {
    display.print(mqtt.connected() ? "MQTT " : "WiFi ");
    display.println(WiFi.localIP());
  } else {
    display.println("WiFi : connexion...");
  }
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

  display.setCursor(0, 14);
  if (isnan(temperature)) display.println("Temp : --");
  else                    display.printf("Temp : %.1f C\n", temperature);

  display.setCursor(0, 26);
  if (isnan(humidite)) display.println("Humi : --");
  else                 display.printf("Humi : %.1f %%\n", humidite);

  display.setCursor(0, 38);
  display.printf("Gaz  : %d\n", gaz);

  display.setCursor(0, 50);
  display.print("PIR  : ");
  display.println(presence ? "PRESENCE !" : "rien");

  display.display();
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
  pinMode(PIN_PIR, INPUT);     // PIR : sortie numérique
  analogReadResolution(12);    // MQ-2 : ADC 12 bits (0..4095)

  configurerWiFi();    // connexion WiFi (portail si 1ʳᵉ fois)
  configurerHeure();   // NTP pour l'horodatage ISO
  Serial.println("Sentinel-X : OLED + DHT22 + MQTT prets");
}

void loop() {
  assurerMQTT();
  mqtt.loop();

  // Détection PIR instantanée : rafraîchit l'OLED dès qu'un mouvement change
  bool pirMaintenant = digitalRead(PIN_PIR) == HIGH;
  if (pirMaintenant != presence) {
    presence = pirMaintenant;
    Serial.println(presence ? ">>> PRESENCE DETECTEE" : ">>> zone libre");
    afficherOLED();
  }

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
