#!/usr/bin/python
#
# SPDX-License-Identifier: Apache-2.0
#

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import os

from ansible.module_utils._text import to_native

from ..module_utils.module import BlockchainModule
from ..module_utils.utils import get_console, get_ordering_service_node_by_module

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: ordering_service_channel
short_description: Manage channels on a Hyperledger Fabric ordering service node
description:
    - Join ordering service nodes to application channels using the channel participation API.
    - This module works with the IBM Support for Hyperledger Fabric software or the Hyperledger Fabric
      Open Source Stack running in a Red Hat OpenShift or Kubernetes cluster.
author: Simon Stone (@sstone1)
options:
    api_endpoint:
        description:
            - The URL for the Fabric operations console.
        type: str
        required: true
    api_authtype:
        description:
            - C(basic) - Authenticate to the Fabric operations console using basic authentication.
              You must provide both a valid API key using I(api_key) and API secret using I(api_secret).
        type: str
        required: true
    api_key:
        description:
            - The API key for the Fabric operations console.
        type: str
        required: true
    api_secret:
        description:
            - The API secret for the Fabric operations console.
            - Only required when I(api_authtype) is C(basic).
        type: str
    api_timeout:
        description:
            - The timeout, in seconds, to use when interacting with the Fabric operations console.
        type: int
        default: 60
    operation:
        description:
            - C(join) - Join an ordering service node to an application channel using a genesis block.
        type: str
        required: true
    ordering_service_node:
        description:
            - The ordering service node to join to the channel.
            - You can pass a string, which is the display name of an ordering service node registered
              with the Fabric operations console.
            - You can also pass a dictionary, which must match the result format of one of the
              M(ordering_service_node_info) or M(ordering_service_node) modules.
        type: raw
        required: true
    name:
        description:
            - The name of the channel.
        type: str
        required: true
    path:
        description:
            - The path to the channel genesis block file.
        type: str
        required: true
notes: []
requirements: []
'''

EXAMPLES = '''
- name: Join the ordering service node to the channel
  hyperledger.fabric_ansible_collection.ordering_service_channel:
    api_endpoint: https://console.example.org:32000
    api_authtype: basic
    api_key: xxxxxxxx
    api_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    operation: join
    ordering_service_node: Ordering Service Node 1
    name: mychannel
    path: channel_genesis_block.bin
'''

RETURN = '''
---
changed:
    description:
        - True if the ordering service node was joined to the channel, false otherwise.
    type: bool
'''


def join(module):

    console = get_console(module)
    ordering_service_node = get_ordering_service_node_by_module(console, module, parameter_name='ordering_service_node')
    path = module.params['path']

    with open(path, 'rb') as file:
        config_block = base64.b64encode(file.read()).decode('utf-8')

    if os.path.getsize(path) == 0:
        raise Exception(f'The channel genesis block at {path} is empty')

    console.submit_config_block(ordering_service_node.id, config_block)
    module.exit_json(changed=True)


def main():

    argument_spec = dict(
        api_endpoint=dict(type='str', required=True),
        api_authtype=dict(type='str', choices=['ibmcloud', 'basic'], required=True),
        api_key=dict(type='str', no_log=True, required=True),
        api_secret=dict(type='str', no_log=True),
        api_timeout=dict(type='int', default=60),
        api_token_endpoint=dict(type='str', default='https://iam.cloud.ibm.com/identity/token'),
        operation=dict(type='str', required=True, choices=['join']),
        ordering_service_node=dict(type='raw', required=True),
        name=dict(type='str', required=True),
        path=dict(type='str', required=True)
    )
    required_if = [
        ('api_authtype', 'basic', ['api_secret']),
        ('operation', 'join', ['api_endpoint', 'api_authtype', 'api_key', 'ordering_service_node', 'name', 'path'])
    ]
    module = BlockchainModule(argument_spec=argument_spec, supports_check_mode=True, required_if=required_if)

    try:
        operation = module.params['operation']
        if operation == 'join':
            join(module)
        else:
            raise Exception(f'Invalid operation {operation}')
    except Exception as e:
        module.fail_json(msg=to_native(e))


if __name__ == '__main__':
    main()
