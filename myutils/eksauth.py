#!/usr/bin/env python

import base64
import boto3
from botocore.signers import RequestSigner

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# https://github.com/aws/aws-cli/blob/4bd5bb8ade16d9eaa032446c72d1ae743e5cb0b2/awscli/customizations/eks/get_token.py

class NewIdentity():
    def __init__(self, role_arn):
        self.role_arn = role_arn

    def get_session(self):
        client = boto3.client('sts')
        response = client.assume_role(
            RoleArn=self.role_arn,
            RoleSessionName="myeks-lambda"
        )
        return boto3.Session(
            aws_access_key_id=response['Credentials']['AccessKeyId'],
            aws_secret_access_key=response['Credentials']['SecretAccessKey'],
            aws_session_token=response['Credentials']['SessionToken']
        )


class EKSAuth(object):

    def __init__(self, cluster_name, role_arn=None, region="us-west-2"):
        self.cluster_name = cluster_name
        self.role_arn = role_arn
        self.region = region

        eks_api = boto3.client('eks',region_name="us-west-2")
        cluster_info = eks_api.describe_cluster(name=self.cluster_name)

        self.api_endpoint = cluster_info['cluster']['endpoint']
        self.certificate = base64.b64decode(cluster_info['cluster']['certificateAuthority']['data'])

    def get_auth_token(self):
        presign_expires = 60

        sts_http_action = 'Action=GetCallerIdentity&Version=2011-06-15'
        sts_http_method = 'GET'

        eks_header = 'x-k8s-aws-id'
        eks_prefix = 'k8s-aws-v1.'

        if self.role_arn:
            session = NewIdentity(role_arn=self.role_arn).get_session()
        else:
            session = boto3.session.Session()

        client = session.client("sts",region_name="us-east-1")
        service_id = client.meta.service_model.service_id

        signer = RequestSigner(
            service_id,
            session.region_name,
            'sts',
            'v4',
            session.get_credentials(),
            session.events
        )

        params = {
            'method': sts_http_method,
            'url': 'https://' + "sts.amazonaws.com" + '/?' + sts_http_action,
            'body': {},
            'headers': {
                eks_header: self.cluster_name
            },
            'context': {}
        }

        signed_url = signer.generate_presigned_url(
            params,
            region_name="us-east-1",
            expires_in=presign_expires,
            operation_name = ''
        )
        logger.debug("Pre-signed URL: {}".format(signed_url))
        logger.info("Caller Identity {}".format(client.get_caller_identity()))
        # This \/ \/ rstrip wasted 3 hours until I looked at aws cli code.
        return (
                eks_prefix +
                base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8').rstrip('=')
        )
