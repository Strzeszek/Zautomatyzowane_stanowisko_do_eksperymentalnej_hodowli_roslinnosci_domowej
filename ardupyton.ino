//Czujnik VOC i C02
#include <Arduino.h>
#include "sensirion_common.h"
#include "sgp30.h"


//Komunikacja WiFi
#include <WiFiS3.h>
char ssid[] = "Orange_Swiatlowod_D2A0";
char pass[] = "FMQYL6T4NH4J";
int status = WL_IDLE_STATUS;
#define DEBUG
WiFiClient client;  


//Czujnik DTH22
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <DHT_U.h>
#define DHTPIN 5 //PIN DHT22
#define DHTTYPE    DHT22     // DHT 22 (AM2302)
DHT_Unified dht(DHTPIN, DHTTYPE);

//Oświetlenie LED
#include <FastLED.h>
#define NUM_LEDS 15 //Ilość diod LED na pasku
#define DATA_PIN 2 //LED pin
#define DATA_PIN2 6 //LED pin v2
CRGB leds[NUM_LEDS];
CRGB leds2[NUM_LEDS];

int delayval = 5000; 
unsigned long startTime; 

const int GroundPIN = A3; //AnalogRead pin dla wilgotności gleby
const int LightPIN = A2;  //AnalogRead pin dla natężenia światła
const int HumidifierPIN = A1;
const int pwm = 3;
const int dir = 4;
const int SolenoidPIN = 7;
const int HeaterPIN = 8;

int groundValue = 0; //wartość startowa dla pomiaru natężenia wilgnotności gleby
int lightValue = 0; //wartość startowa dla pomiaru natężenia światła
const int minBrightness = 0;      // Minimalne natężenie panela LED
const int maxBrightness = 255;    // Maksymalne natężenie panela LED
int StartBrightness = 120;

float setpoint_temp = 21;
float setpoint_airhum = 0.0;
int setpoint_grhum = 0;
int setpoint_light = 0;

//Dla komunikacji serial
const char *serverAddress = "192.168.1.55"; 
const int serverPort = 5678;

void startDelay() {
  startTime = millis();
}


bool checkDelay(unsigned long duration) {
  return (millis() - startTime >= duration);
}

void printWifiData() {
  IPAddress ip = WiFi.localIP();
  Serial.print("IP Address: ");
  Serial.println(ip);
  byte mac[6];
  WiFi.macAddress(mac);
  Serial.print("MAC address: ");
  printMacAddress(mac);
}

void printCurrentNet() {
  Serial.print("SSID: ");
  Serial.println(WiFi.SSID());
  byte bssid[6];
  WiFi.BSSID(bssid);
  Serial.print("BSSID: ");
  printMacAddress(bssid);
  long rssi = WiFi.RSSI();
  Serial.print("signal strength (RSSI):");
  Serial.println(rssi);
  byte encryption = WiFi.encryptionType();
  Serial.print("Encryption Type:");
  Serial.println(encryption, HEX);
  Serial.println();
}

void printMacAddress(byte mac[]) {
  for (int i = 5; i >= 0; i--) {
    if (mac[i] < 16) {
      Serial.print("0");
    }
    Serial.print(mac[i], HEX);
    if (i > 0) {
      Serial.print(":");
    }
  }
  Serial.println();
}

void setup() {

  startDelay();


  //Część dla WiFi
  Serial.begin(115200);
    while (!Serial) {
    ; 
  }

  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("Communication with WiFi module failed!");
    // don't continue
    while (true);
  }

  String fv = WiFi.firmwareVersion();
  if (fv < WIFI_FIRMWARE_LATEST_VERSION) {
    Serial.println("Please upgrade the firmware");
  }

  while (status != WL_CONNECTED) {
    Serial.print("Attempting to connect to WPA SSID: ");
    Serial.println(ssid);
    status = WiFi.begin(ssid, pass);
    delay(10000);
  }

  Serial.print("You're connected to the network");
  printCurrentNet();
  printWifiData();




  s16 err;
  u16 scaled_ethanol_signal, scaled_h2_signal;
  Serial.begin(115200);
  Serial.println("serial start!!");


  #if defined(ESP8266)
  pinMode(15, OUTPUT);
  digitalWrite(15, 1);
  Serial.println("Set wio link power!");
  delay(500);
  #endif
  while (sgp_probe() != STATUS_OK) {
      Serial.println("SGP failed");
      while (1);
  }
  err = sgp_measure_signals_blocking_read(&scaled_ethanol_signal,
                                          &scaled_h2_signal);
  if (err == STATUS_OK) {
      Serial.println("get ram signal!");
  } else {
      Serial.println("error reading signals");
  }
  err = sgp_iaq_init();

  dht.begin();
  sensor_t sensor;
  dht.temperature().getSensor(&sensor);
  dht.humidity().getSensor(&sensor);
  FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, NUM_LEDS);
  FastLED.addLeds<WS2812B, DATA_PIN2, GRB>(leds2, NUM_LEDS);
  FastLED.setBrightness(StartBrightness);
  FastLED.show();



  pinMode(dir, OUTPUT);
  pinMode(pwm, INPUT);   
  pinMode(GroundPIN, INPUT);
  pinMode(LightPIN, INPUT);
  pinMode(HumidifierPIN, OUTPUT);
  pinMode(SolenoidPIN, OUTPUT);
  pinMode(HeaterPIN, OUTPUT);
  
}

void setBrightness() {
  for ( int i = 0; i < NUM_LEDS; i++ ) {
    leds[i] = CRGB::Purple;
    leds2[i] = CRGB::Purple;
    FastLED.setBrightness(StartBrightness);
  }
  FastLED.show();
}

void changeBrightness(int val){
    const int margin = 5; 
    if (val < (setpoint_light - margin) && (StartBrightness >= 0 && StartBrightness <= 254))
    {
        StartBrightness = StartBrightness + 1;
        setBrightness();
    }
    else if (val > (setpoint_light + margin) && (StartBrightness >= 1 && StartBrightness <= 255))
    {
        StartBrightness = StartBrightness - 1;
        setBrightness();
    }
}

void DC (unsigned char p, unsigned char d){
  digitalWrite(dir, d);
  if (d == LOW){
    analogWrite(pwm, p);
  }
  else{
    analogWrite(pwm, 255 - p);
  }
}

void water(int hum){
  static unsigned long wateringStartTime = 0;
  const unsigned long wateringDuration = 5000; 

  if (hum < setpoint_grhum) {
    if (wateringStartTime == 0) {
      wateringStartTime = millis(); 
      digitalWrite(SolenoidPIN, HIGH);
    }


    if (millis() - wateringStartTime >= wateringDuration) {
      digitalWrite(SolenoidPIN, LOW); 
      wateringStartTime = 0;           
    }
}
}


void loop() {
  sensors_event_t event;
  dht.temperature().getEvent(&event);
  float temperatura = event.temperature;
  dht.humidity().getEvent(&event);
  float wilgpow = event.relative_humidity; 

  groundValue = analogRead(GroundPIN);
  lightValue = analogRead(LightPIN); 

  s16 err = 0;
  u16 tvoc_ppb, co2_eq_ppm;
  err = sgp_measure_iaq_blocking_read(&tvoc_ppb, &co2_eq_ppm);

  
if (Serial.available() > 0) {

    String receivedData = Serial.readStringUntil('\n');
    processReceivedData(receivedData);
  }

if(temperatura > (setpoint_temp+0.2)){
    digitalWrite(HeaterPIN, LOW);
    DC (255, HIGH);
  }

if(temperatura < (setpoint_temp-0.2)){
    digitalWrite(HeaterPIN, HIGH); 
    DC (50,HIGH);
  }

  if(setpoint_airhum > wilgpow)
  {
    digitalWrite(HumidifierPIN, HIGH); 
  }
  else digitalWrite(HumidifierPIN, LOW);

  water(groundValue);

changeBrightness(lightValue);
 if (checkDelay(5000)) {
  sendSensorData(temperatura, wilgpow, tvoc_ppb, co2_eq_ppm, groundValue, lightValue, StartBrightness);
  startDelay();
  }
}

void sendSensorData(float temperature, float humidity, int voc, int co2, int groundValue, int lightValue, int StartBrightness) {


  if (client.connect(serverAddress, serverPort)) {
    Serial.println("Połączono z serwerem Pythona");
    String data = String(temperature) + "," + String(humidity) + "," + String(voc) + "," + String(co2) + "," + String(groundValue) + "," + String(lightValue) + "," + String(StartBrightness);
    client.print(data);
    Serial.println("Dane wysłane do serwera Pythona");
    client.stop();

  } else {
    Serial.println("Błąd połączenia z serwerem Pythona");
  }
}

void processReceivedData(String data) {
  int delimiterIndex = data.indexOf(':');
  String tableName = data.substring(0, delimiterIndex);
  float averageValue = data.substring(delimiterIndex + 1).toFloat();

  if (tableName == "currentvalue_temperatura") {
    setpoint_temp = averageValue;
  }

  if (tableName == "currentvalue_wilgotnoscpowietrza") {
    setpoint_airhum = averageValue;
  }

  if (tableName == "currentvalue_wilgotnoscgleby") {
    setpoint_grhum = averageValue;
  }

  if (tableName == "currentvalue_natezenieswiatla") {
    setpoint_light = averageValue;
  }
}
