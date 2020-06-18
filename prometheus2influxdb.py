#!/usr/bin/env python
#-*- coding: utf-8 -*-
import time
import copy
import requests
from influxdb import InfluxDBClient

def send_influx(TABLE_NAME, TARGET, NAMESPACE, TARGET_CLUSTER, VALUE, TIMESTAMP):
    json_body = [
        {
            "measurement": TABLE_NAME,
            "tags": {
                "target": TARGET,
                "namespace": NAMESPACE,
                "target_cluster": TARGET_CLUSTER,
            },
            "fields": {
                "value": VALUE
            },
            "time": TIMESTAMP * 1000000000
        }
    ]
    influx_client.write_points(json_body)

class analyze_prom():
    def __init__(self, cluster_addr, cluster_name):
        self.cluster_addr = "http://%s" % cluster_addr
        self.cluster_name = cluster_name
        self.query_url = '{0}/api/v1/query'.format(self.cluster_addr)
        self.query_range_url = '{0}/api/v1/query_range'.format(self.cluster_addr)
        self.local_timestamp = int(time.time())
        self.pod_detail = {}
        self.node_detail = {}
        self.pod_params = [
            ("pod_cpu_usage_1m","query_range", 'sum (irate (container_cpu_usage_seconds_total{namespace=~".*", \
                                    pod_name=~".*", container_name!="POD"}[1m])) \
                                        by (container_name,pod_name,namespace,instance)'),

            ("pod_cpu_requested","query_range", 'sum (container_spec_cpu_shares{namespace=~".*", \
                                    pod_name=~".*", container_name!="POD"}) \
                                        by (container_name,pod_name,namespace,instance)'),

            ("pod_cpu_limit","query_range", 'sum (container_spec_cpu_quota{namespace=~".*", \
                                    pod_name=~".*", container_name!="POD"}) \
                                        by (container_name,pod_name,namespace,instance)'),

            ("pod_mem_usage_1m","query_range", 'sum (avg_over_time (container_memory_working_set_bytes{namespace=~".*", \
                                    pod_name=~".*", container_name!="POD"}[1m])) \
                                        by (container_name,pod_name,namespace,instance)'),

            ("pod_mem_limit","query_range", 'sum (container_spec_memory_limit_bytes{namespace=~".*", \
                                    pod_name=~".*", container_name!="POD"}) \
                                        by (container_name,pod_name,namespace,instance)'),

            ("pod_network_in","query_range", 'sum (irate (container_network_receive_bytes_total{namespace=~".*", \
                                    pod_name=~".*"}[1m])) by (container_name,pod_name,namespace,instance)'),

            ("pod_network_out","query_range", 'sum (irate (container_network_transmit_bytes_total{namespace=~".*", \
                                    pod_name=~".*"}[1m])) by (container_name,pod_name,namespace,instance)'),

            ("pod_fs_usage","query", 'container_fs_usage_bytes{namespace=~".*", pod_name=~".*"}'),

            ("pod_fs_writes","query_range", 'sum (irate (container_fs_writes_bytes_total{namespace=~".*", \
                                    pod_name=~".*"}[1m])) by (container_name,pod_name,namespace,instance)'),

            ("pod_fs_reads","query_range", 'sum (irate (container_fs_reads_bytes_total{namespace=~".*", \
                                    pod_name=~".*"}[1m])) by (container_name,pod_name,namespace,instance)'),
        ]
        self.node_params = [
            ("node_load_1m","query", 'node_load1{instance=~".*"}'),
            ("node_cpu_total","query_range", 'count (irate(node_cpu_seconds_total{mode="idle", instance=~".*"}[1m])) \
                                    by (mode, instance)'),
            ("node_cpu","query_range", 'sum (irate(node_cpu_seconds_total{instance=~".*"}[1m])) \
                                    by (mode, instance)'),
            ("node_mem_used","query", 'node_memory_MemTotal_bytes{instance=~".*"} \
                                                - node_memory_MemFree_bytes{instance=~".*"} \
                                                  - node_memory_Buffers_bytes{instance=~".*"} \
                                                    - node_memory_Cached_bytes{instance=~".*"}'),
            ("node_mem_total","query", 'node_memory_MemTotal_bytes{instance=~".*"}'),
            ("node_network_in","query_range", 'sum (irate(node_network_receive_bytes_total{instance=~".*",\
                                                    device="eth0"}[1m])) by (device, instance)'),
            ("node_network_out","query_range", 'sum (irate(node_network_transmit_bytes_total{instance=~".*",\
                                                    device="eth0"}[1m])) by (device, instance)'),
            ("node_fs_total","query", 'node_filesystem_size_bytes{instance=~".*",fstype=~"ext4|xfs"}'),
            ("node_fs_avail","query", 'node_filesystem_avail_bytes{instance=~".*",fstype=~"ext4|xfs"}'),
            ("node_fs_reads","query_range", 'max(irate(node_disk_read_bytes_total{instance=~".*"}[2m])) \
                                                by (device, instance)'),
            ("node_fs_writes","query_range", 'max(irate(node_disk_written_bytes_total{instance=~".*"}[2m])) \
                                                by (device, instance)'),
        ]

    def query_node(self):
        for item, ql_type, promQL in self.node_params:
            if ql_type == "query":
                url = self.query_url
                params = {}
                params["query"] = promQL
            else:
                url = self.query_range_url
                params = {}
                params["query"] = promQL
                # params["query"] = promQL.replace("PRE_pod_name",pod_name)
                params["start"] = self.local_timestamp - 2*60
                params["end"] = self.local_timestamp
                params["step"] = 1
            try:
                response = requests.get(url, timeout=10, params=params)
                result = response.json()['data']['result']
            except Exception as e:
                print url
                print params
                print e
                continue
            for info in result:
                # print info
                metric = info["metric"]
                if metric != {}:
                    instance = metric["instance"]

                    if ql_type == "query":
                        value = info["value"][-1]
                    else:
                        value = info["values"][-1][-1]

                    if self.node_detail.get(instance, "") == "":
                        self.node_detail[instance] = {}
                        self.node_detail[instance]["target_type"] = "node"
                    if self.node_detail[instance].get("k8s_name","") == "":
                        self.node_detail[instance]["k8s_name"] = self.cluster_name
                    if "node_fs" in item:
                        device = metric["device"]
                        item_fs = "%s_%s" % (item, device)
                        self.node_detail[instance][item_fs] = float('%.5f' % float(value))
                    elif "node_cpu" == item:
                        mode = metric["mode"]
                        item_fs = "%s_%s" % (item, mode)
                        self.node_detail[instance][item_fs] = float('%.5f' % float(value))
                    elif "_network_" in item:
                        value = float(value) * 8
                        self.node_detail[instance][item] = float('%.5f' % float(value))
                    else:
                        self.node_detail[instance][item] = float('%.5f' % float(value))
        return self.node_detail
        # for k,v in self.node_detail.items():
        #     print k,v
    def query_pod(self):
        for item, ql_type, promQL in self.pod_params:
            if ql_type == "query":
                url = self.query_url
                params = {}
                params["query"] = promQL
            else:
                url = self.query_range_url
                params = {}
                params["query"] = promQL
                # params["query"] = promQL.replace("PRE_pod_name",pod_name)
                params["start"] = self.local_timestamp - 2*60
                params["end"] = self.local_timestamp
                params["step"] = 1
            try:
                response = requests.get(url, timeout=10, params=params)
                result = response.json()['data']['result']
            except Exception as e:
                print url
                print params
                print e
                continue
            for info in result:
                metric = info["metric"]
                if metric.get("container_name","") != "":
                    container_name = metric["container_name"]
                    pod_name = metric["pod_name"]
                    namespace = metric["namespace"]
                    instance = metric["instance"]

                    if ql_type == "query":
                        value = info["value"][-1]
                    else:
                        value = info["values"][-1][-1]

                    if self.pod_detail.get(pod_name, "") == "":
                        self.pod_detail[pod_name] = {}
                        self.pod_detail[pod_name]["target_type"] = "pod"
                    if self.pod_detail[pod_name].get("container_name","") == "":
                        self.pod_detail[pod_name]["container_name"] = container_name
                    if self.pod_detail[pod_name].get("namespace","") == "":
                        self.pod_detail[pod_name]["namespace"] = namespace
                    if self.pod_detail[pod_name].get("k8s_node","") == "":
                        self.pod_detail[pod_name]["k8s_node"] = instance
                    if self.pod_detail[pod_name].get("k8s_name","") == "":
                        self.pod_detail[pod_name]["k8s_name"] = self.cluster_name

                    if "_network_" in item:
                        value = float(value) * 8
                        self.pod_detail[pod_name][item] = float('%.5f' % float(value))
                    else:
                        self.pod_detail[pod_name][item] = float('%.5f' % float(value))
        return self.pod_detail
        # for k,v in self.pod_detail.items():
        #     print k,v
def run(prome_server_list):
    for cluster_addr, cluster_name in prome_server_list:
        print cluster_addr, cluster_name
        analyze = analyze_prom(cluster_addr, cluster_name)
        pod_detail = analyze.query_pod()
        node_detail = analyze.query_node()
        for pod, data in pod_detail.items():
            try:
                if data["pod_cpu_usage_1m"] == 0:
                    data["pod_cpu_usage_1m_percent"] = float(0)
                else:
                    data["pod_cpu_usage_1m"] = data["pod_cpu_usage_1m"] * 1000
                    if data.get("pod_cpu_limit","") != "":
                        data["pod_cpu_limit"] = data["pod_cpu_limit"] / 100
                        data["pod_cpu_usage_1m_percent"] = data["pod_cpu_usage_1m"] / data["pod_cpu_limit"]
                        data["pod_cpu_usage_1m_percent_request"] = data["pod_cpu_usage_1m"]/data["pod_cpu_requested"]
                    else:
                        data["pod_cpu_usage_1m_percent"] = float(0)
                        data["pod_cpu_usage_1m_percent_request"] = data["pod_cpu_usage_1m"]/data["pod_cpu_requested"]

                if data["pod_mem_usage_1m"] == 0:
                    data["pod_mem_usage_1m_percent"] = float(0)
                elif data["pod_mem_limit"] == 0:
                    data["pod_mem_usage_1m_percent"] = float(99.99)
                else:
                    data["pod_mem_usage_1m_percent"] = data["pod_mem_usage_1m"]/data["pod_mem_limit"]
            except Exception as e:
                print pod
                print e
        for node, data in node_detail.items():
            # print node, data
            data["node_mem_used_percent"] = data["node_mem_used"] / data["node_mem_total"]
            for item,value in data.items():
                if item.startswith("node_cpu") == True and item != "node_cpu_total":
                    if value == 0:
                        data[item + "_percent"] = float(0)
                    else:
                        data[item + "_percent"] = value/data["node_cpu_total"]

        detail_merge = {}
        detail_merge.update(pod_detail)
        detail_merge.update(node_detail)
        #print detail_merge
        TIMESTAMP = int(time.time())
        for target, data in detail_merge.items():
            for item, value in data.items():
                TABLE_NAME = item
                TARGET = target
                if data["target_type"] == "pod":
                    NAMESPACE = data.get("namespace","default")
                else:
                    NAMESPACE = "k8s_node"
                TARGET_CLUSTER = data["k8s_name"]
                VALUE = value
                # print (TABLE_NAME, TARGET, NAMESPACE, TARGET_CLUSTER,VALUE)
                send_influx(TABLE_NAME, TARGET, NAMESPACE, TARGET_CLUSTER, VALUE, TIMESTAMP)

if __name__ == "__main__":
    influx_client = InfluxDBClient(
        host='9.5.5.9',
        port=1234,
        username='monitor',
        password='YK123',
        database='monitor',
        ssl=True,
        verify_ssl=True)

    prome_server_list = [
        ("9.5.5.9:9090", "baidu-bj-k8s-0001"),
    ]

    while True:
        print("------------- start -------------------")
        start_time = time.time()
        run(prome_server_list)
        print("------------- end -------------------")
        while True:
            if time.time() - start_time > 60:
                break
            time.sleep(1)
