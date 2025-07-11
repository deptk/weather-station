#include <WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_BMP085.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <WiFiClientSecure.h>
#include <ESPmDNS.h>
#include <NetworkUdp.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>

// ===== WiFi =====
const char* ssid = "YOU_SSID";
const char* password = "YOU_WiFi_PASSWORD";

WiFiClientSecure secured_client;

// Период обновления двнных с датчиков
unsigned long lastUpdate = 0;
const unsigned long updateInterval = 10 * 60 * 1000;  // 10 минут

// Инициализация DS18B20
#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);

// Инициализация BMP180
Adafruit_BMP085 bmp;

// Инициализация OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Переменные
float outdoorTemp;
float indoorTemp;
float pressure;
float pressure_hpa;
float pressure_mmhg;

// Вывод показаний на OLED
void updateOLED() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(2);

  oled.setCursor(0, 0);
  oled.print("T: ");
  oled.print(outdoorTemp, 1);

  oled.setCursor(0, 18);
  oled.print("P: ");
  oled.print(pressure_mmhg, 1);

  oled.setCursor(0, 36);
  oled.print("P: ");
  oled.print(pressure_hpa, 1);

  oled.display();
}

// Отправка двнных в БД
void sendToPhpServer() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin("http://192.168.ХХХ.ХХХ/ws/submit.php");  // Замените на ваш URL
    http.addHeader("Content-Type", "application/json");

    String json = "{\"outdoor\":" + String(outdoorTemp, 2) + ",\"indoor\":" + String(indoorTemp, 2) + ",\"pressure_mmhg\":" + String(pressure_mmhg, 2) + ",\"pressure_hpa\":" + String(pressure_hpa, 2) + "}";

    int response = http.POST(json);
    Serial.print("PHP Server response: ");
    Serial.println(response);
    http.end();
  } else {
    Serial.println("WiFi не подключен, не могу отправить данные на PHP сервер");
  }
}

// Обновление данных с датчиков, вывод на OLED и отправка в БД
void readAndUpdateAll() {
  ds18b20.requestTemperatures();
  outdoorTemp = ds18b20.getTempCByIndex(0);
  indoorTemp = bmp.readTemperature();
  pressure = bmp.readPressure();
  pressure_hpa = pressure / 100; // BMP180 дает данные в Па (паскали), переводим в гПа (гектопаскали)
  pressure_mmhg = pressure / 133.322; // Переводим Па в миллиметры ртутного столба (для алгоритма Замбретти)

  updateOLED();
  sendToPhpServer();
}

void setup() {
  // Инициализация последовательного соединения и отправка данных для отладки
  Serial.begin(115200);

  WiFi.begin(ssid, password);
  Serial.print("Подключение к WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi подключен: " + WiFi.localIP().toString());

  secured_client.setInsecure();

  // Инициализация датчиков
  ds18b20.begin();
  if (!bmp.begin()) {
    Serial.println("BMP180 не найден");
    while (true)
      ;
  }

  // OLED
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("OLED не найден"));
    while (true)
      ;
  }

  // Первичное считывание данных с датчиков после включения ESP32
  readAndUpdateAll();
  // Сброс счетчика периода обновления
  lastUpdate = millis();

  // OTA для прошивки ESP32 по сети
  ArduinoOTA
    .onStart([]() {
      String type;
      if (ArduinoOTA.getCommand() == U_FLASH) {
        type = "sketch";
      } else {  // U_SPIFFS
        type = "filesystem";
      }
      // NOTE: if updating SPIFFS this would be the place to unmount SPIFFS using SPIFFS.end()
      Serial.println("Start updating " + type);
    })
    .onEnd([]() {
      Serial.println("\nEnd");
    })
    .onProgress([](unsigned int progress, unsigned int total) {
      Serial.printf("Progress: %u%%\r", (progress / (total / 100)));
    })
    .onError([](ota_error_t error) {
      Serial.printf("Error[%u]: ", error);
      if (error == OTA_AUTH_ERROR) {
        Serial.println("Auth Failed");
      } else if (error == OTA_BEGIN_ERROR) {
        Serial.println("Begin Failed");
      } else if (error == OTA_CONNECT_ERROR) {
        Serial.println("Connect Failed");
      } else if (error == OTA_RECEIVE_ERROR) {
        Serial.println("Receive Failed");
      } else if (error == OTA_END_ERROR) {
        Serial.println("End Failed");
      }
    });
  ArduinoOTA.begin();
}

void loop() {
  ArduinoOTA.handle();

// Счетчик обновления данных с датчиков
  if (millis() - lastUpdate > updateInterval) {
    readAndUpdateAll();
    lastUpdate = millis();
  }

  // Небольшая задержка для стабильности
  delay(10);
}

