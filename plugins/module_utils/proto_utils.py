#!/usr/bin/python
#
# SPDX-License-Identifier: Apache-2.0
#

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from .file_utils import get_temp_file

import json
import os
import subprocess


def _stderr_text(error):
    stderr = getattr(error, 'stderr', None)
    if stderr is None:
        return ''
    if isinstance(stderr, bytes):
        return stderr.decode('utf-8', errors='replace').strip()
    return str(stderr).strip()


def proto_to_json(proto_type, proto_input):
    temp_file = get_temp_file()
    try:
        subprocess.run([
            'configtxlator', 'proto_decode', f'--type={proto_type}', f'--output={temp_file}'
        ], input=proto_input, text=False, close_fds=True, check=True, capture_output=True)
        with open(temp_file, 'rb') as file:
            return json.load(file)
    except subprocess.CalledProcessError as e:
        raise Exception(f'Failed to decode {proto_type}: {_stderr_text(e)}')
    finally:
        os.remove(temp_file)


def json_to_proto(proto_type, json_input):
    json_data = json.dumps(json_input).encode('utf-8')
    temp_file = get_temp_file()
    try:
        subprocess.run([
            'configtxlator', 'proto_encode', f'--type={proto_type}', f'--output={temp_file}'
        ], input=json_data, text=False, close_fds=True, check=True, capture_output=True)
        with open(temp_file, 'rb') as file:
            return file.read()
    except subprocess.CalledProcessError as e:
        raise Exception(f'Failed to encode {proto_type}: {_stderr_text(e)}')
    finally:
        os.remove(temp_file)
