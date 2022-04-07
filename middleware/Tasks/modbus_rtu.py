import getmac
import Poller.poller_task as poller
import pprint
import traceback
import time
import psutil
import os
import ast
import sys
import Protocols.mqtt as MyMQTT
from time import strftime, localtime
import json

import paho.mqtt.client as mqtt
import Poller.poller_control as control

pp = pprint.PrettyPrinter(indent=2)
ParentFolder = os.path.abspath('..')


wait_delay = False
comport = "" 
Subsclient = mqtt.Client()
# Function to get current memory usage (only for development stage)

def wait_until(somepredicate, timeout, period=0.25):
  mustend = time.time() + timeout
  while time.time() < mustend:
    if somepredicate: 
        return True
    time.sleep(period)
  return False

def get_process_memory():
    process = psutil.Process(os.getpid())
    return [process.memory_info().rss, process.memory_full_info().rss]

def process_data_subscribe(client, userdata, message):
    global Subsclient
    try:
        sub_data = json.loads(message.payload)
        if sub_data["port"] == comport:
            print("Get Subscribe data with topic: "+ message.topic + " in port: " + comport)
            if wait_until(wait_delay, 10, 0.1):
                if control.ModbusRTU_Control(sub_data):
                    print("succes control modbus")
                    sub_data["status"] = "succes control modbus"
                    Subsclient.publish( message.topic + "_status", json.dumps(sub_data))
                else:
                    print("failed control modbus")
                    sub_data["status"] = "failed control modbus"
                    Subsclient.publish( message.topic + "_status", json.dumps(sub_data))
            else:
                print("failed control modbus")
                sub_data["status"] = "failed control modbus"
                Subsclient.publish( message.topic + "_status", json.dumps(sub_data))
    except Exception as e:
        pass


def modbusrtu_polling_task(profile_list, protocol_setting_list, interval, mqtt_config, comm_port):
    global wait_delay, comport, Subsclient

    comport = comm_port
    dev_num = len(profile_list)
    
    print("starting modbus RTU polling task...")
    # print(profile_list)
    # print(protocol_setting_list)
    # print(dev_num)

    errlog = open(os.getcwd() + "/errlog.txt", "a")
    errlog.write("{0} I'm still running!\n".format(
        strftime("%Y-%m-%d %H:%M:%S")))
    errlog.close()

    dev_poller = []
    for i in range(dev_num):
        print(profile_list[i]["name"], "is running")
        dev_poller.append(poller.ModbusRTU(
            profile_list[i], protocol_setting_list[i]))
        #print(poller.ModbusRTU(profile_list[i], protocol_setting_list[i]))
        # print(str(dev_poller))
    print("poller success")
    # Read Polling Service Status
    with open(os.getcwd() + '/stat.temp') as file:
        FINISH = ast.literal_eval(file.read())

    # MQTT config
    mqtt_enable = mqtt_config['enable']
    broker_address = mqtt_config['broker_address']
    broker_port = mqtt_config['broker_port']
    retain = mqtt_config['retain']
    qos = mqtt_config['qos']

    username = mqtt_config['username']
    password = mqtt_config['password']
    print("MQTT success")
    
    #config to Subscribe data
    Subsclient.on_message=process_data_subscribe 
    Subsclient.connect(broker_address, broker_port)
    Subsclient.loop_start()
    Subsclient.subscribe(mqtt_config['sub_topic_modbusRTU'])
    #print("Connecting to broker for Subscriber")
    
    while (not FINISH):
        try:            
            for i in range(dev_num):
                # print('[PROFILE LIST]')
                # print(profile_list)
                # print('[protocol_setting_list]')
                # print(protocol_setting_list)

                topic = mqtt_config['pub_topic'][0] + \
                     str(profile_list[i]["topic"])

                #topic = mqtt_config['pub_topic'][0]

                try:
                    data = dev_poller[i].poll()
                    # print(data)
                    # Publish data to MQTT Broker IF MQTT SERVICE ENABLED
                    for item in data:
                        #username = item["username"]
                        #password = item["password"]
                        if mqtt_enable:
                            try:
                                mqtt_client = MyMQTT.Client(broker_address, broker_port, retain, qos, username,
                                                            password)
                                mqtt_client.set_usr_pw(username, password)
                                mqtt_client.connect()
                                mqtt_client.publish(topic,  item["data"])
                                # DYNAMIC: ADDITIONAL DATA RTU

                                #print('[protocol setting identifier]')
                                #print(protocol_setting_list[i])

                                #rtu_number_address = protocol_setting_list[i].get(
                                #    'address')

                                #mqtt_client.publish(topic, {
                                #    'mac': getmac.get_mac_address(),
                                #    'protocol_type': 'Modbus RTU',
                                #    'number_address': rtu_number_address,
                                #    'value': json.dumps(item["data"])
                                #})

                                errlog = open(os.getcwd() + "/errlog.txt", "a")
                                errlog.write("{0} {1} publish check\n".format(
                                    strftime("%Y-%m-%d %H:%M:%S", localtime()), profile_list[i]["name"]))
                                errlog.close()
                            except Exception as e:
                                print(e)
                                tb = traceback.format_exc()
                                print(tb)
                                errlog = open(os.getcwd() + "/errlog.txt", "a")
                                errlog.write("{0} {1} Error: {2}\n".format(
                                    strftime("%Y-%m-%d %H:%M:%S", localtime()), profile_list[i]["name"], str(e)))
                                errlog.close()
                                pass
                except Exception as e:
                    print(e)
                    print("publish failed")
                    mqtt_client = MyMQTT.Client(broker_address, broker_port, retain, qos, username,
                                                password)
                    mqtt_client.set_usr_pw(username, password)
                    mqtt_client.connect()
                    mqtt_client.publish(
                        topic, profile_list[i]["name"] + " data acquisition failed")
                    errlog = open(os.getcwd() + "/errlog.txt", "a")
                    errlog.write("{0} {1} Error: {2}\n".format(
                        strftime("%Y-%m-%d %H:%M:%S", localtime()), profile_list[i]["name"], str(e)))
                    errlog.close()
                    pass
            errlog = open(os.getcwd() + "/errlog.txt", "a")
            errlog.write("{0} {1} data acquisition check\n".format(
                strftime("%Y-%m-%d %H:%M:%S", localtime()), profile_list[i]["name"]))
            errlog.close()
            # Read Polling Service Status
            with open(os.getcwd() + '/stat.temp') as file:
                FINISH = ast.literal_eval(file.read())

            # Wait for next data polling
            wait_delay = True
            for i in range(interval):
                if i == interval -2:
                    wait_delay = False
                time.sleep(1)
           

        except KeyboardInterrupt:
            print('Interrupted')
            break

        except:
            errlog.write("{0} {1} Error: your program sucks it goes out of the loop\n".format(
                strftime("%Y-%m-%d %H:%M:%S", localtime()), profile_list[i]["name"]))
            raise
            # Wait for next data polling
            time.sleep(interval)
            tb = traceback.format_exc()
            print("exception occured")
            print(tb)
        errlog = open(os.getcwd() + "/errlog.txt", "a")
        errlog.write("{0} loop check\n".format(strftime("%Y-%m-%d %H:%M:%S")))
        errlog.close()
