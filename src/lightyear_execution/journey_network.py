"""Separate database-lane policy. Does not widen ExecutionPolicy's network none."""
from dataclasses import dataclass
import re
from .contracts import ExecutionContractError


@dataclass(frozen=True)
class InternalOnlyNetwork:
    run_id: str

    def __post_init__(self):
        if not re.fullmatch(r'journey-[a-f0-9]{32}', self.run_id):
            raise ExecutionContractError('Invalid local journey resource owner')

    def create_args(self,name):
        return ['network','create','--internal','--label','lightyear.journey='+self.run_id,name]

    def verify(self,network,containers):
        if network.get('Internal') is not True or network.get('Labels',{}).get('lightyear.journey') != self.run_id:
            raise ExecutionContractError('Database lane network is not internal and owned')
        for c in containers:
            # Docker Desktop inserts a loopback entry with an empty HostPort on
            # internal networks. It is not a published port: Ports stays empty.
            # Refuse concrete bindings, non-loopback placeholders, and any actual
            # forwarding. Never treat an assigned ephemeral port as empty.
            configured=c['HostConfig'].get('PortBindings') or {}
            actual=c['NetworkSettings'].get('Ports') or {}
            published=any(actual.values()) or any(
                binding.get('HostPort') or binding.get('HostIp')!='127.0.0.1'
                for bindings in configured.values() for binding in bindings)
            if (c['Config'].get('Labels',{}).get('lightyear.journey') != self.run_id
                    or published or c['HostConfig'].get('Privileged')
                    or c['HostConfig']['NetworkMode'] != network['Name']
                    or set(c['NetworkSettings']['Networks']) != {network['Name']}):
                raise ExecutionContractError('Container escaped its private lane network')
        return True
