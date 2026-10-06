"""Run only under the dedicated Tower identity after explicit operator setup approval."""
import argparse
import hashlib
import json
import os
import ctypes
from pathlib import Path

from lightyear_calibration.contracts import canonical
from lightyear_control_tower.console import ConsoleService, provision


def run(authority, root, output):
    name = ctypes.create_unicode_buffer(256)
    size = ctypes.c_ulong(len(name))
    if os.name != 'nt' or not ctypes.windll.advapi32.GetUserNameW(name, ctypes.byref(size)) or name.value.lower() != 'lyb06tower':
        raise ValueError('Dedicated Windows Tower identity required')
    authority, root, output = map(Path, (authority, root, output))
    if authority.exists(): raise ValueError('Existing authority cannot be replaced')
    provision(authority, 'ms94-b06', 'howard-weale', 'Howard Weale')
    service = ConsoleService(root, authority)
    try:
        event = service.grant_roles('howard-weale', ['operator','campaign-authorizer'],
            reason='Howard explicitly approved the B06 Tower setup proposal r8 in chat on 2026-10-06; no group or model run authorized.',
            workloads=[])
        # Positive read-open under Tower identity, without exporting key bytes.
        with authority.with_suffix('.key.pem').open('rb'): pass
        public = service.public_key
        result = {'artifact_type':'ms94-b06-tower-provisioning/1','scope':'ms94-b06',
            'public_key_sha256':hashlib.sha256(public).hexdigest(),
            'role_event_sha256':event['content_sha256'], 'operator_id':'howard-weale',
            'roles':['operator','campaign-authorizer'], 'tower_key_read_open_succeeded':True,
            'group_decisions_issued':0, 'model_calls':0, 'docker_commands':0,
            'review':'operator review; not independent attestation'}
        with (output/'authority.public.pem').open('xb') as stream: stream.write(public)
        with (output/'provisioning.json').open('xb') as stream: stream.write(canonical(result))
    finally: service.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('authority','root','output'): parser.add_argument('--'+field,required=True,type=Path)
    args=parser.parse_args(); run(args.authority,args.root,args.output)
