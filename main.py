#!/usr/bin/env python

import json
import urllib.request
import time

import boto3

from kubernetes import client

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

from myutils import eksauth

CLUSTER_CERT_PATH = '/tmp/eks_cert_path'

def get_current_asg(cluster_name=None):
    session = boto3.Session()
    client = session.client('autoscaling')

    asg_prefix = "{}-worker-".format(cluster_name)

    paginator = client.get_paginator('describe_auto_scaling_groups')
    page_iterator = paginator.paginate(
        PaginationConfig={'PageSize': 100}
    )
    asgs = list(page_iterator.search(
        'AutoScalingGroups[] | [?starts_with(AutoScalingGroupName, `{}`) && MinSize > `0` && MaxSize > `0` && DesiredCapacity > `0`]'.format(asg_prefix)
    ))

    if len(asgs) != 1:
        for asg in asgs:
            logger.info(asg['AutoScalingGroupName'])
        raise Exception("We didn't find exactly one ASG")
    else:
        return asgs[0]

def get_new_asg(cluster_name=None):
    session = boto3.Session()
    client = session.client('autoscaling')

    asg_prefix = "{}-worker-".format(cluster_name)

    paginator = client.get_paginator('describe_auto_scaling_groups')
    page_iterator = paginator.paginate(
        PaginationConfig={'PageSize': 100}
    )
    asgs = list(page_iterator.search(
        'AutoScalingGroups[] | [?starts_with(AutoScalingGroupName, `{}`) && MinSize == `0` && MaxSize == `0` && DesiredCapacity == `0`]'.format(asg_prefix)
    ))

    if len(asgs) != 1:
        for asg in asgs:
            logger.info(asg['AutoScalingGroupName'])
        raise Exception("We didn't find exactly one ASG")
    else:
        return asgs[0]

def scale_out_asg(asg_name, min_size, max_size, desired):
    session = boto3.Session()
    client = session.client('autoscaling')
    client.update_auto_scaling_group(AutoScalingGroupName=asg_name, MinSize=min_size, MaxSize=max_size, DesiredCapacity=desired)

def scale_in_asg():
    """
    ToDo: Mark nodes unschedulable, use pod eviction api and then delete node
    :return:
    """
    pass

def cluster_healthcheck(healthcheck_url=None):
    req = urllib.request.Request(healthcheck_url)
    for i in range(0, 10):
        try:
            with urllib.request.urlopen(req, timeout=1) as response:
                http_status = response.status
                http_body = response.read()
                break
        except urllib.error.URLError as e:
            print(e.reason)
            time.sleep(1)

def k8_connection():
    cluster = eksauth.EKSAuth(cluster_name="myeks")
    with open(CLUSTER_CERT_PATH, 'wb') as fin:
        fin.write(cluster.certificate)

    configuration = client.Configuration()
    configuration.host = cluster.api_endpoint
    configuration.ssl_ca_cert = CLUSTER_CERT_PATH
    configuration.api_key['authorization'] = cluster.get_auth_token()
    configuration.api_key_prefix['authorization'] = 'Bearer'
    return configuration

def k8_get_pods(namespace=None):
    """
    Print pods in given namespace
    :return:
    """
    conn = k8_connection()
    api = client.ApiClient(conn)
    v1 = client.CoreV1Api(api)
    # Get all the pods
    pods = v1.list_namespaced_pod(namespace)
    return pods.items


def wait_for_nodes(min_nodes=2, asg_name="myeks-worker-green"):
    """
    Wait for min node to be available in specified ASG
    :param min_nodes:
    :param asg_name:
    :return:
    """
    conn = k8_connection()
    api = client.ApiClient(conn)
    v1 = client.CoreV1Api(api)

    for i in range(1,10):
        nodes = v1.list_node(pretty=False, label_selector="eks_worker_group == {}".format(asg_name)).items
        ready_nodes = [n for n in nodes for c in n.status.conditions if c.reason == "KubeletReady"]
        num_ready_nodes = len(ready_nodes)
        if num_ready_nodes >= min_nodes:
            break
        else:
            time.sleep(30)


wait_for_nodes(asg_name="myeks-worker-green")


def lambda_handler(event, context):
    if event['cluster_name']:
        cluster_name = event['cluster_name']
    else:
        cluster_name = context.function_name.split("_")[0]

    if event['healthcheck_url']:
        healthcheck_url = event['healthcheck_url']
    else:
        healthcheck_url = "example.com"

    current_active_asg = get_current_asg()
    k8_get_pods(namespace="default")
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }