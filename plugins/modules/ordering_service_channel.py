#!/usr/bin/python
#
# SPDX-License-Identifier: Apache-2.0
#

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import os
import subprocess
import tempfile
import urllib.parse

from ansible.module_utils._text import to_native

from ..module_utils.module import BlockchainModule
from ..module_utils.utils import (get_console, get_identity_by_module,
                                  get_ordering_service_node_by_module)

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
            - C(join) - Join an ordering service node to an application channel using a genesis block,
              via the channel participation (C(osnadmin)) API.
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
    tls_identity:
        description:
            - The TLS client identity to use for mutual TLS with the ordering service node admin
              (channel participation) endpoint.
            - This identity must be enrolled against the TLS certificate authority for the ordering
              organization, as the orderer admin endpoint requires mutual TLS.
            - You can pass a string, which is the path to the JSON file where the enrolled identity is stored.
            - You can also pass a dict, which must match the result format of one of the
              M(enrolled_identity_info) or M(enrolled_identity) modules.
        type: raw
        required: true
    osnadmin_url:
        description:
            - The URL of the ordering service node admin (channel participation) endpoint.
            - If not specified, the admin URL registered for the ordering service node with the
              Fabric operations console is used.
        type: str
    name:
        description:
            - The name of the channel.
        type: str
        required: true
    path:
        description:
            - The path to the channel genesis (config) block file.
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
    tls_identity: Ordering Org Admin TLS.json
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


def _get_admin_endpoint(module, ordering_service_node):

    # Prefer an explicitly specified admin URL, otherwise fall back to the
    # admin URL registered for the ordering service node.
    osnadmin_url = module.params['osnadmin_url'] or ordering_service_node.osnadmin_url
    if not osnadmin_url:
        raise Exception(
            'No admin (channel participation) endpoint is available for the ordering service node. '
            'Specify osnadmin_url, or ensure the ordering service node exposes an admin endpoint.'
        )

    # osnadmin expects a host:port, not a URL.
    parsed = urllib.parse.urlparse(osnadmin_url)
    if parsed.netloc:
        return parsed.netloc
    return osnadmin_url


def join(module):

    console = get_console(module)
    ordering_service_node = get_ordering_service_node_by_module(console, module, parameter_name='ordering_service_node')
    name = module.params['name']
    path = module.params['path']

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise Exception(f'The channel genesis block at {path} is missing or empty')

    # Get the TLS client identity required for mutual TLS with the admin endpoint.
    tls_identity = get_identity_by_module(module, parameter_name='tls_identity')
    if tls_identity.hsm or tls_identity.private_key is None:
        raise Exception('The TLS identity must include a private key and cannot use an HSM')

    admin_endpoint = _get_admin_endpoint(module, ordering_service_node)

    # Write out the TLS CA root cert, client cert, and client key for osnadmin.
    ca_file = client_cert_file = client_key_file = None
    try:
        ca_fd, ca_file = tempfile.mkstemp()
        os.write(ca_fd, base64.b64decode(ordering_service_node.tls_ca_root_cert))
        os.close(ca_fd)

        cert_fd, client_cert_file = tempfile.mkstemp()
        os.write(cert_fd, tls_identity.cert)
        os.close(cert_fd)

        key_fd, client_key_file = tempfile.mkstemp()
        os.write(key_fd, tls_identity.private_key)
        os.close(key_fd)

        args = [
            'osnadmin', 'channel', 'join',
            '--channelID', name,
            '--config-block', path,
            '-o', admin_endpoint,
            '--ca-file', ca_file,
            '--client-cert', client_cert_file,
            '--client-key', client_key_file,
        ]
        module.json_log({'msg': 'running osnadmin channel join', 'args': args})
        process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, close_fds=True)
        output = process.stdout or ''
        module.json_log({'msg': 'osnadmin finished', 'rc': process.returncode, 'output': output})

        # osnadmin returns the HTTP status of the participation API call.
        # 201 - successfully joined. 405 - channel already exists on this OSN (idempotent).
        if 'Status: 201' in output:
            module.exit_json(changed=True)
        elif 'Status: 405' in output or 'already exists' in output:
            module.exit_json(changed=False)
        elif process.returncode == 0:
            module.exit_json(changed=True)
        else:
            raise Exception(f'Failed to join ordering service node to channel {name}: {output.strip()}')
    finally:
        for temp_file in [ca_file, client_cert_file, client_key_file]:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)


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
        tls_identity=dict(type='raw', required=True),
        osnadmin_url=dict(type='str'),
        name=dict(type='str', required=True),
        path=dict(type='str', required=True)
    )
    required_if = [
        ('api_authtype', 'basic', ['api_secret']),
        ('operation', 'join', ['api_endpoint', 'api_authtype', 'api_key', 'ordering_service_node', 'tls_identity', 'name', 'path'])
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
