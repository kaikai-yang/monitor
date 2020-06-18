#!/usr/bin/env python
# -*- coding:utf-8 -*-
import time
from influxdb import InfluxDBClient
from bs4 import BeautifulSoup
import requests

def main_page(edge_nginx, domain, form_action):
    curl = "http://" +  edge_nginx
    headers = {'Host': domain}
    count = 0
    while count < 3:
        try:
            print "....get main page try [%s].. " % count
            resp = requests.get(curl, headers=headers, timeout=5, verify=False)
            soup = BeautifulSoup(resp.content,"html.parser")
            page_form_action = soup.find("input")["name"].encode("utf-8")
            if form_action == page_form_action:
                return True
            count += 1
        except Exception as e:
            print e
            count += 1
    return False

def send_influx(TABLE_NAME, TARGET, VALUE, timestamp):
    json_body = [
        {
            "measurement": TABLE_NAME,
            "tags": {
                "target": TARGET,
            },
            "fields": {
                "value": VALUE
            },
            "time": timestamp * 1000000000
        }
    ]
    influx_client.write_points(json_body)

def run():
    TABLE_NAME = "web_monitor"
    for domain, form_action in domain_info_list:
        for edge_nginx, hostname in edge_nginx_list:
            TARGET = "%s_%s_%s_%s" % (domain, edge_nginx, hostname, form_action)
            print("---- %s ----" % TARGET)
            print time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            timestamp = int(time.time())
            result = main_page(edge_nginx, domain, form_action)
            if result == True:
                VALUE = 1
            else:
                VALUE = 2
            print "VALUE: %s" % VALUE
            #send_influx(TABLE_NAME, TARGET, VALUE,timestamp)

if __name__ == '__main__':
    influx_client = InfluxDBClient(
        host='1.1.1.1',
        port=1234,
        username='monitor',
        password='YK123',
        database='monitor',
        ssl=True,
        verify_ssl=True)
    edge_nginx_list = [
        ("220.181.38.149", "baidu-bj-nginx-0001"),
    ]
    domain_info_list = [
        ("www.baidu.com", "bdorz_come"),
    ]
    while True:
        print("------------- start -------------------")
        run()
        print("------------- end -------------------")
        time.sleep(60)
