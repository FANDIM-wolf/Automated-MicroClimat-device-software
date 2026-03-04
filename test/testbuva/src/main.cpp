#include <Arduino.h>

#include <GyverDS18.h>
GyverDS18Single ds(15);  // пин
GyverDS18Single ds2(14);

String temp1;
String temp2;

void setup() {
  pinMode (13,OUTPUT);
  pinMode (12,OUTPUT);
  digitalWrite (13,1);
  digitalWrite (12,0);
  Serial.begin(9600);
  ds.setResolution(12);
  ds2.setResolution(12);
}
void loop() {
    // тикер, вызывать в loop
    // по готовности и успешному чтению
    if (!ds.tick()) {
    
        //  temp1
        ds.requestTemp();
        ds.readTemp();
        float f = ds.getTemp();
        String ds1 = String(f);
        String untilds1 = "gpio 15 ";
        temp1 = untilds1 + ds1;





        //  temp2
        ds2.requestTemp();
        ds2.readTemp();
        float f2 = ds2.getTemp();
        String ds2 = String(f2);
        String untilds2 = "gpio 14 ";
        temp2 = untilds2 + ds2;
        



    }

    //Отправка данных в Serial
    if (Serial.available()> 0){
        
        char in_data = Serial.read();

        Serial.println(":");

       Serial.println(temp1);

        Serial.println(",");

       Serial.println(temp2); 

       Serial.println(";");
        

    }

    
}