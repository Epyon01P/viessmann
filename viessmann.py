# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 21:39:31 2020
A minimal implementation of a Modbus piggyback for Viessmann heat pumps (HP).
The serial interface hardware is controlled by messages over the MQTT bus.
The programme reads in a JSON file (viessmann.josn) containing the registers 
to read, briefly disables the communication between HP and thermostat thereby 
making itself the bus master, requests the registers, then relinquishes 
back control over the bus to the thermostat. This takes about 2-20s.
The register contents are published in JSON format to the MQTT broker.
@author: Epyon01P
"""

import time
import minimalmodbus
import serial
import sys
import json
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as subscribe

brokers_out={"broker1":"localhost"}

#For debugging purposes, it's possible to give a register id through the command line
try: 
    regid = int(sys.argv[1])
    data = list([dict({'register': regid, 'name': 'test', 'type': 'numeric', 'unit': '', 'multiplier': 1, 'publish': False})])
except IndexError:
    try:
        with open('viessmann.json') as f:
            data = json.load(f)
    except OSError:
        data = list([dict({'register': 200, 'name': 'serial_number', 'type': 'numeric', 'unit': '', 'multiplier': 1, 'publish': True})]) #a default fallback register id

#Connect to the MQTT bus
client=mqtt.Client("viessmann")
client.connect(brokers_out["broker1"])
#First, check if Viessmann monitoring is enabled
msg1 = subscribe.simple("local/viessmann/monitoring", keepalive=10) #software enable
msg2 = subscribe.simple("gpio/status/viessmann-monitoring", keepalive=10) #hardware enable (override)
if msg1.payload.decode() == "enabled" and msg2.payload.decode() == "enabled":
    #Set RS485 transceiver to Viessmann specifications
    instrument = minimalmodbus.Instrument('/dev/ttyUSB1', 1, debug = False)
    instrument.serial.baudrate = 9600
    instrument.serial.parity   = serial.PARITY_EVEN
    instrument.serial.timeout = 0.1
    #Interrupt communication between thermostat and heat pump. 
    #Don't worry thermostat, we'll take good care of the heat pump.
    resptopic="gpio/write/viessmann-modbus"
    resp = "enabled"
    client.publish(resptopic,resp)
    #Check if the Modbus interface has been enabled
    msg = subscribe.simple("gpio/status/viessmann-modbus", keepalive=10)
    if msg.payload.decode() == "enabled":
        #Request the required registers from the heat pump and publish it on the MQTT bus.
        for register in data:
            regid = int(register['register'])
            attempts = 0
            while attempts < 10: #try each register ten times before moving on
                try:
                    var = instrument.read_register(regid, 0)
                    var = var / register['multiplier']
                    resp = {'name': register['name'], 'value': var, 'unit': register['unit'], 'timestamp' : int(time.time())}
                    resp= json.dumps(resp, ensure_ascii=False)
                    print(resp)
                    topic="viessmann/" + register['name']
                    #client=mqtt.Client("viessmann")
                    #client.connect(brokers_out["broker1"])
                    client.publish(topic,resp)
                    #client.disconnect()
                    break
                except IOError:
                    attempts += 1
                    if attempts == 10: print("Modbus error for register " + str(regid) + ", skipping")
                    time.sleep(0.5)
        #Give back control over heat pump to thermostat.
        #No heat pumps were harmed during the execution of this programme.
        resp = "disabled"
        client.publish(resptopic,resp)
    else:
        print("Viessmann Modbus communication disabled")
else:
    print("Viessmann monitoring disabled")
client.disconnect()
