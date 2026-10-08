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
#ifdef DEV_PLAIN_MQTT
#include <WiFiClient.h>       // DEV : client TCP EN CLAIR (1883, sans TLS)
#else
#include <WiFiClientSecure.h> // client TCP chiffré (TLS)
#endif
#include <WiFiManager.h>      // tzapu/WiFiManager — portail de config WiFi
#include <PubSubClient.h>     // knolleary — client MQTT
#include <ArduinoJson.h>      // bblanchon — sérialisation JSON (v7)
#include <Preferences.h>      // stockage persistant (IP du broker) en flash NVS
#ifdef USE_HMAC
#include "mbedtls/md.h"       // HMAC-SHA256 (anti-injection) — actif si -DUSE_HMAC
#endif
#include <time.h>
#include "ca_cert.h"          // certificat PUBLIC de la CA interne (CA_CERT)
#ifdef USE_SECRETS
#include "secrets.h"          // config EN DUR (WiFi + IP broker) — ni portail ni téléphone
#endif

// Réception des alertes serveur : nécessaire à l'affichage OLED ET aux LEDs.
#if defined(OLED_ALERTS) || defined(STATUS_LEDS)
#define ALERTES_RX 1
#endif

// Clé HMAC par défaut si secrets.h ne la définit pas : garantit que l'env
// esp32dev-full COMPILE même avec un ancien secrets.h (à changer en prod).
#if defined(USE_HMAC) && !defined(SENTINEL_HMAC_SECRET)
#define SENTINEL_HMAC_SECRET "change-moi-cle-partagee-equipe-6"
#endif

// --- Broches ---
const int PIN_DHT = 4;   // DHT22      sur GPIO 4  (température + humidité)
const int PIN_PIR = 27;  // PIR HC-SR501 sur GPIO 27 (présence, sortie numérique)
const int PIN_MQ2 = 34;  // MQ-2       sur GPIO 34 (gaz, entrée analogique ADC1)

// --- Constantes réseau / MQTT ---
const char* AP_NAME        = "SENTINEL-X-SETUP";  // réseau WiFi de configuration
const char* MQTT_TOPIC     = "sentinel/sensors";  // topic attendu par la Brique 3
#ifdef ALERTES_RX
const char* MQTT_ALERT_TOPIC = "sentinel/alerts"; // alertes serveur -> OLED + LEDs
const unsigned long ALERTE_AFFICHAGE_MS = 30000;  // durée d'affichage d'une alerte (30 s)
#endif
#ifdef STATUS_LEDS
const int PIN_LED_VERT   = 26;   // LED verte  (D26) : tout va bien
const int PIN_LED_ORANGE = 14;   // LED orange (D14) : avertissement / déconnecté
const int PIN_LED_ROUGE  = 13;   // LED rouge  (D13) : alerte critique
#endif
#ifdef DEV_PLAIN_MQTT
const int   MQTT_PORT      = 1883;                 // DEV : MQTT en clair (broker dev)
#else
const int   MQTT_PORT      = 8883;                 // MQTTS (TLS) — plus de port en clair
#endif
const int   PORTAL_TIMEOUT = 180;                  // s : ferme le portail si inactif

// --- Cadence de lecture ---
const unsigned long PERIODE_MS = 2000;  // DHT22 : 1 lecture / 2 s maximum
const unsigned long MQTT_RETRY_MS = 5000;  // délai entre deux tentatives de connexion MQTT

// --- Objets matériels / réseau ---
Adafruit_SSD1306 display(128, 64, &Wire, -1);
bool oledPresent = false;   // vrai si l'OLED répond en I²C (0x3C ou 0x3D)
DHT dht(PIN_DHT, DHT22);
#ifdef DEV_PLAIN_MQTT
WiFiClient wifiClient;         // DEV : pas de TLS
#else
WiFiClientSecure wifiClient;
#endif
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
int   gaz          = 0;      // GAZ NORMALISÉ : 0 au repos, monte avec le gaz (= brut - baseline)
// Auto-calibration du MQ-2 : on mesure la baseline (air propre) au démarrage,
// puis on envoie l'ÉCART -> 0 au repos, comme les autres capteurs/groupes.
const unsigned long GAS_WARMUP_MS = 60000;   // chauffe du MQ-2 : on ignore la 1ʳᵉ minute
const unsigned long GAS_CALIB_MS  = 80000;   // on calibre la baseline entre 60 et 80 s
int   gazBaseline  = 0;
bool  gazCalibre   = false;
long  gazSomme     = 0;
int   gazEchant    = 0;
bool  presence     = false;  // PIR : true = mouvement détecté
unsigned long derniereLecture = 0;
#ifdef ALERTES_RX
char  derniereAlerte[48] = "";   // dernière alerte reçue du serveur (texte court)
char  alerteSeverite[12] = "";   // "CRITICAL" / "WARNING" / "INFO"
unsigned long alerteRecueMs = 0; // horodatage (millis) de réception de l'alerte
#endif

// ---------------------------------------------------------------------------
//  OLED : petit utilitaire d'affichage (jusqu'à 3 lignes)
// ---------------------------------------------------------------------------
void oledLignes(const char* l1, const char* l2 = "", const char* l3 = "") {
  if (!oledPresent) return;   // pas d'écran initialisé -> ne pas écrire (évite un crash mémoire)
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
#ifdef USE_SECRETS
  // ---- Config EN DUR (secrets.h) : aucun portail, aucun téléphone ----
  strncpy(brokerIp, BROKER_IP, sizeof(brokerIp) - 1);
  brokerIp[sizeof(brokerIp) - 1] = '\0';
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);   // reconnexion automatique en tâche de fond

  // Diagnostic : liste les réseaux visibles -> on voit si le hotspot est là.
  Serial.printf("Je cherche le reseau : \"%s\"\n", WIFI_SSID);
  int nRes = WiFi.scanNetworks();
  bool hotspotVu = false;
  Serial.printf("Scan WiFi : %d reseau(x) visible(s) :\n", nRes);
  for (int i = 0; i < nRes; i++) {
    Serial.printf("   - \"%s\"  (signal %d dBm)\n", WiFi.SSID(i).c_str(), WiFi.RSSI(i));
    if (WiFi.SSID(i) == String(WIFI_SSID)) hotspotVu = true;
  }
  Serial.println(hotspotVu ? ">>> Hotspot TROUVE dans le scan."
                           : ">>> Hotspot ABSENT du scan ! (nom different ? hotspot eteint ? trop loin ?)");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  oledLignes("WiFi (secrets)", WIFI_SSID, "connexion...");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() != WL_CONNECTED) {
    // PAS de redémarrage : le système continue EN LOCAL (capteurs/OLED/LEDs) et
    // le WiFi se reconnecte tout seul en arrière-plan. Évite tout reboot-loop.
    // status : 1=SSID introuvable, 4=mot de passe/association refuse, 6=echec.
    Serial.printf("\nWiFi pas connecte (status=%d). ", WiFi.status());
    Serial.println(hotspotVu ? "Hotspot vu mais refuse -> verifie le MOT DE PASSE."
                             : "Hotspot pas vu -> nom exact ? allume ? a portee ?");
    oledLignes("WiFi hors ligne", "capteurs OK", "reconnexion...");
    return;
  }
  Serial.printf("WiFi OK (secrets) - IP %s | broker %s:%d\n",
                WiFi.localIP().toString().c_str(), brokerIp, MQTT_PORT);
#else
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
#ifdef DEV_PLAIN_MQTT
  bool configIncomplete = strlen(brokerIp) == 0;                         // DEV : seule l'IP suffit
#else
  bool configIncomplete = strlen(brokerIp) == 0 || strlen(mqttUser) == 0 || strlen(mqttPass) == 0;
#endif
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
#endif  // USE_SECRETS

  // TLS : l'ESP32 n'accepte que les brokers dont le certificat est signé par
  // notre CA ET émis pour l'adresse saisie au portail (sinon : connexion refusée).
#ifndef DEV_PLAIN_MQTT
  wifiClient.setCACert(CA_CERT);
#endif
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

#ifdef ALERTES_RX
// Réception d'une alerte serveur (topic sentinel/alerts) -> OLED + LEDs.
// Payload JSON attendu : { "type": "...", "details": { "context":"", "severity":"" } }
void surMessageMQTT(char* topic, byte* payload, unsigned int longueur) {
  if (strcmp(topic, MQTT_ALERT_TOPIC) != 0) return;
  JsonDocument doc;
  if (deserializeJson(doc, payload, longueur)) return;  // JSON invalide : on ignore
  const char* type = doc["type"] | "ALERTE";
  const char* ctx  = doc["details"]["context"] | "";
  const char* sev  = doc["details"]["severity"] | "WARNING";
  snprintf(derniereAlerte, sizeof(derniereAlerte), "%s %s", type, ctx);
  snprintf(alerteSeverite, sizeof(alerteSeverite), "%s", sev);
  alerteRecueMs = millis();
  Serial.printf(">>> ALERTE recue [%s] : %s\n", alerteSeverite, derniereAlerte);
}
#endif

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
#ifdef DEV_PLAIN_MQTT
  if (mqtt.connect(clientId.c_str())) {              // DEV : broker anonyme (1883)
    Serial.println("MQTT connecte (dev, sans TLS)");
#ifdef ALERTES_RX
    mqtt.subscribe(MQTT_ALERT_TOPIC);                 // reçoit les alertes serveur
#endif
    return;
  }
  Serial.printf("MQTT : echec (state=%d)\n", mqtt.state());
#else
  if (mqtt.connect(clientId.c_str(), mqttUser, mqttPass)) {
    Serial.println("MQTTS connecte (TLS + authentification)");
#ifdef ALERTES_RX
    mqtt.subscribe(MQTT_ALERT_TOPIC);                 // reçoit les alertes serveur
#endif
    return;
  }
  // state : -2 = TCP/TLS impossible (certificat, IP, pare-feu) ; 4/5 = identifiants refusés
  char erreurTls[100] = "";
  wifiClient.lastError(erreurTls, sizeof(erreurTls));
  Serial.printf("MQTTS : echec (state=%d) %s\n", mqtt.state(), erreurTls);
#endif
}

#ifdef USE_HMAC
// Calcule la signature HMAC-SHA256 (hex) d'un message, avec la clé partagée.
// Le format signé DOIT être identique à security/message_signing.py :
//   temp|humidity|gas|presence|timestamp   (temp/humidity à 1 décimale)
void signerMessage(float temp, float hum, int gas, int pres,
                   const char* ts, char* sigHex, size_t sigLen) {
  char canonique[160];
  snprintf(canonique, sizeof(canonique), "%.1f|%.1f|%d|%d|%s",
           temp, hum, gas, pres, ts);

  uint8_t hmac[32];
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_hmac(info,
                  (const uint8_t*)SENTINEL_HMAC_SECRET, strlen(SENTINEL_HMAC_SECRET),
                  (const uint8_t*)canonique, strlen(canonique), hmac);

  for (int i = 0; i < 32 && (size_t)(i * 2 + 2) < sigLen; i++)
    snprintf(sigHex + i * 2, 3, "%02x", hmac[i]);
}
#endif

void publierMesure() {
  // Format EXACT attendu par le client Python (Brique 3) :
  // {temp, humidity, gas, presence, timestamp}
  String tsStr = horodatageISO();      // conservé vivant (String, pas un temporaire)
  const char* ts = tsStr.c_str();
  int presenceInt = presence ? 1 : 0;

  JsonDocument doc;
  doc["temp"]      = temperature;
  doc["humidity"]  = humidite;
  doc["gas"]       = gaz;              // MQ-2 : valeur brute ADC (0..4095)
  doc["presence"]  = presenceInt;      // PIR  : 1 = présence, 0 = rien
  doc["timestamp"] = ts;

#ifdef USE_HMAC
  // Signature anti-injection : le serveur rejettera tout faux message.
  char sigHex[65] = "";
  signerMessage(temperature, humidite, gaz, presenceInt, ts, sigHex, sizeof(sigHex));
  doc["sig"] = sigHex;
#endif

  char payload[256];
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
  presence    = digitalRead(PIN_PIR) == HIGH; // PIR : HIGH = mouvement

  int brut = analogRead(PIN_MQ2);            // MQ-2 : valeur brute 0..4095 (12 bits)
  unsigned long t = millis();
  if (!gazCalibre) {
    // Phase de calibration : on moyenne la baseline en air propre (après chauffe).
    if (t > GAS_WARMUP_MS) { gazSomme += brut; gazEchant++; }
    if (t > GAS_CALIB_MS && gazEchant > 0) {
      gazBaseline = (int)(gazSomme / gazEchant);
      gazCalibre = true;
      Serial.printf("MQ-2 calibre : baseline air propre = %d ADC\n", gazBaseline);
    }
    gaz = 0;                                 // on envoie 0 pendant la calibration
  } else {
    // Suivi du minimum : si on lit plus bas que la baseline (air encore plus
    // propre / dérive), on recale -> le repos reste toujours ~0.
    if (brut < gazBaseline) gazBaseline = brut;
    int delta = brut - gazBaseline;          // écart par rapport à l'air propre
    gaz = delta > 0 ? delta : 0;             // 0 au repos, monte avec le gaz
  }
}

void afficherSerie() {
  if (isnan(temperature) || isnan(humidite))
    Serial.printf("DHT22 : lecture KO | Gaz=%d  PIR=%d\n", gaz, presence);
  else
    Serial.printf("T=%.1f C  H=%.1f %%  Gaz=%d  PIR=%d\n",
                  temperature, humidite, gaz, presence);
}

void afficherOLED() {
  if (!oledPresent) return;   // pas d'écran : on ne tente rien (évite tout blocage I²C)
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

#ifdef OLED_ALERTS
  // Si une alerte récente est arrivée, on l'affiche en bannière inversée.
  if (derniereAlerte[0] != '\0' && millis() - alerteRecueMs < ALERTE_AFFICHAGE_MS) {
    display.fillRect(0, 0, 128, 12, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setCursor(2, 2);
    display.println("! ALERTE SENTINEL-X");
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 16);
    display.println(derniereAlerte);
    display.setCursor(0, 40);
    display.printf("T:%.0fC H:%.0f%%\n", temperature, humidite);
    display.setCursor(0, 52);
    display.printf("Gaz:%d PIR:%d\n", gaz, presence ? 1 : 0);
    display.display();
    return;
  }
#endif

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

#ifdef STATUS_LEDS
// Met à jour les 3 LEDs selon l'état du système (une seule allumée) :
//   ROUGE  = alerte critique récente
//   ORANGE = avertissement récent OU déconnecté (WiFi/MQTT)
//   VERT   = tout va bien (connecté, aucune alerte récente)
void majStatutLeds() {
  bool connecte = (WiFi.status() == WL_CONNECTED) && mqtt.connected();
  bool recente  = derniereAlerte[0] != '\0' && millis() - alerteRecueMs < ALERTE_AFFICHAGE_MS;
  bool critique = recente && strcmp(alerteSeverite, "CRITICAL") == 0;
  // orange seulement pour un vrai AVERTISSEMENT (pas pour un simple INFO).
  bool warning  = recente && strcmp(alerteSeverite, "WARNING") == 0;

  digitalWrite(PIN_LED_ROUGE,  critique ? HIGH : LOW);
  digitalWrite(PIN_LED_ORANGE, (!critique && (warning || !connecte)) ? HIGH : LOW);
  digitalWrite(PIN_LED_VERT,   (!critique && !warning && connecte) ? HIGH : LOW);
}
#endif

// ---------------------------------------------------------------------------
//  setup / loop
// ---------------------------------------------------------------------------
void setup() {
  // NB : on GARDE le détecteur de brownout actif (il protège la flash). Si la
  // carte reset/plante au démarrage du WiFi -> c'est un manque de courant :
  // alim 5V solide (bon câble/chargeur 2A), MQ-2 sur 5V, LEDs avec résistances.
  Serial.begin(115200);
  delay(400);
  Serial.println("\n=== SENTINEL-X demarrage ===");   // imprime AVANT l'I2C
  Serial.flush();

  // Résistances internes de tirage : le bus I2C ne "flotte" pas si l'OLED est
  // absente, ce qui évite tout blocage au démarrage.
  pinMode(21, INPUT_PULLUP);
  pinMode(22, INPUT_PULLUP);
  Wire.begin(21, 22);  // I²C : SDA=21, SCL=22
  Wire.setTimeOut(50); // ms : jamais de blocage I2C

  // Scanner I²C : liste les périphériques ET mémorise l'adresse de l'OLED.
  // (Approche éprouvée : on démarre l'écran sur l'adresse RÉELLEMENT détectée.)
  Serial.println("--- Scan I2C (SDA=GPIO21, SCL=GPIO22) ---");
  byte adresseOled = 0;
  int nbI2C = 0;
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  peripherique I2C trouve a 0x%02X\n", addr);
      if (addr == 0x3C || addr == 0x3D) adresseOled = addr;  // OLED SSD1306
      nbI2C++;
    }
  }
  if (nbI2C == 0)
    Serial.println("  AUCUN peripherique I2C ! -> SDA/SCL inverses ou debranches, ou 3V3/GND absents.");
  Serial.println("-----------------------------------------");

  // Démarre l'écran sur l'adresse détectée. Si l'OLED est absente, on NE BLOQUE
  // PAS — capteurs/WiFi/MQTT/LEDs continuent de fonctionner.
  if (adresseOled != 0 && display.begin(SSD1306_SWITCHCAPVCC, adresseOled)) {
    oledPresent = true;
    display.setTextColor(SSD1306_WHITE);
    Serial.printf("OLED OK a l'adresse 0x%02X\n", adresseOled);
  } else {
    oledPresent = false;
    Serial.println("OLED introuvable - verifie SDA=21/SCL=22/3V3/GND. On continue sans ecran.");
  }

  dht.begin();
  // INPUT_PULLDOWN : si le fil OUT du PIR fait faux contact, on lit "non"
  // (au lieu d'un "oui" bloqué dû à une entrée flottante). Le PIR, quand il
  // est bien branché, pilote quand même la broche normalement.
  pinMode(PIN_PIR, INPUT_PULLDOWN);
#ifdef STATUS_LEDS
  pinMode(PIN_LED_VERT, OUTPUT);
  pinMode(PIN_LED_ORANGE, OUTPUT);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  digitalWrite(PIN_LED_ORANGE, HIGH);  // orange au démarrage (pas encore connecté)
#endif
  analogReadResolution(12);    // MQ-2 : ADC 12 bits (0..4095)

  configurerWiFi();    // connexion WiFi (portail si 1ʳᵉ fois)
  configurerHeure();   // NTP pour l'horodatage ISO
#ifdef ALERTES_RX
  mqtt.setCallback(surMessageMQTT);  // réception des alertes serveur
#endif
  Serial.println("Sentinel-X : OLED + DHT22 + MQTT prets");
}

void loop() {
  assurerMQTT();
  mqtt.loop();
#ifdef STATUS_LEDS
  majStatutLeds();   // LEDs vert/orange/rouge selon l'état du système
#endif

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
