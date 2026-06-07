# SPDX-FileCopyrightText: 2017 Open Networking Foundation
#
# SPDX-License-Identifier: Apache-2.0
from . import p4_device_config_pb2 as p4config_pb2

from .switch import SwitchConnection


def buildDeviceConfig(bmv2_json_file_path=None):
    "Return raw BMv2 JSON bytes for SetForwardingPipelineConfig."
    with open(bmv2_json_file_path, "rb") as handle:
        return handle.read()


class Bmv2SwitchConnection(SwitchConnection):
    def buildDeviceConfig(self, **kwargs):
        return buildDeviceConfig(**kwargs)
