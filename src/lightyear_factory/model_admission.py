"""F2 proof admission; no signing, reservation, key discovery or network calls."""
from datetime import datetime, timezone
import json
from hashlib import sha256
import re
from pathlib import Path
import subprocess
from lightyear_control_tower.factory_policy import FactoryDecisions
from .contracts import ContractError, canonical_hash
from .model_versions import require_snapshot


class FactoryModelAdmission:
    """Verify committed plan/proof bytes with externally supplied current trust."""
    def __init__(self, root, plan_path, proof_path, contract_path, *, public_key, trusted_head):
        self.root = Path(root).resolve()
        self.paths = (plan_path, proof_path, contract_path)
        if public_key is None or not callable(trusted_head):
            raise ContractError('factory-model-external-trust-required')
        self.public_key, self.trusted_head = public_key, trusted_head

    @classmethod
    def from_external_trust(cls, root, plan_path, proof_path, contract_path, trust_path):
        root=Path(root).resolve(); config=Path(trust_path).absolute()
        def external(path):
            cursor=path
            while cursor!=cursor.parent:
                if cursor.is_symlink() or getattr(cursor,'is_junction',lambda:False)():
                    raise ContractError('factory-model-trust-link')
                cursor=cursor.parent
            resolved=path.resolve()
            if resolved==root or root in resolved.parents or not resolved.is_file():
                raise ContractError('factory-model-external-trust-required')
            raw=resolved.read_bytes()
            if len(raw)>65536:raise ContractError('factory-model-trust-size')
            return raw
        initial=json.loads(external(config))
        if initial.get('scope')!='factory':raise ContractError('factory-model-trust-scope')
        key_path=config.parent/initial['public_key']; public=external(key_path)
        def current_head():
            current=json.loads(external(config))
            if (current.get('scope')!='factory' or current.get('public_key')!=initial['public_key']
                    or external(key_path)!=public or not re.fullmatch('[0-9a-f]{64}',current.get('journal_head_sha256',''))):
                raise ContractError('factory-model-trust-changed')
            return current['journal_head_sha256']
        current_head()
        return cls(root,plan_path,proof_path,contract_path,public_key=public,trusted_head=current_head)

    def _committed_json(self, relative):
        from .workspace import IsolatedWorkspace
        IsolatedWorkspace._strict_relative(relative)
        path = self.root/relative
        cursor = path
        while cursor != self.root:
            if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                raise ContractError('factory-model-evidence-link')
            cursor = cursor.parent
        raw = path.read_bytes()
        if len(raw)>8*1024*1024:
            raise ContractError('factory-model-evidence-size')
        committed = subprocess.check_output(['git', '--no-optional-locks', '-C', str(self.root),
                                            'show', 'HEAD:'+relative])
        if raw != committed:
            raise ContractError('factory-model-evidence-not-committed')
        return json.loads(raw)

    def verify_runtime(self, order, *, source_root, input_paths, policy, read_manifest=None, now=None):
        """Bind the actual controller inputs; no nonce, credential or model use."""
        from .workspace import IsolatedWorkspace
        from lightyear_execution.contracts import ExecutionPolicy
        if Path(source_root).resolve()!=self.root or type(policy) is not ExecutionPolicy:
            raise ContractError('factory-model-runtime-root-or-policy')
        if not isinstance(input_paths,dict) or set(input_paths)!={'scope','freeze','workspace','execution_policy'}:
            raise ContractError('factory-model-runtime-inputs')
        admitted=self.verify_plan(order,now=now)
        plan=self._committed_json(self.paths[0])
        if canonical_hash(plan,{'content_sha256'})!=admitted['plan_sha256']:
            raise ContractError('factory-model-plan-changed')
        loaded={}
        for name,path in input_paths.items():
            candidate=Path(path)
            if not candidate.is_absolute():candidate=self.root/candidate
            try:relative=candidate.relative_to(self.root).as_posix()
            except ValueError:raise ContractError('factory-model-runtime-path') from None
            IsolatedWorkspace._strict_relative(relative)
            bound=plan['bound_inputs'][name]
            if relative!=bound['path']:
                raise ContractError('factory-model-runtime-path')
            loaded[name]=self._committed_json(relative)
            if sha256((self.root/relative).read_bytes()).hexdigest()!=bound['sha256']:
                raise ContractError('factory-model-runtime-bytes')
        manifest=loaded['workspace']
        if not isinstance(manifest,dict) or not manifest:
            raise ContractError('factory-model-runtime-workspace')
        for path,digest in manifest.items():
            IsolatedWorkspace._strict_relative(path)
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
                raise ContractError('factory-model-runtime-workspace')
        if read_manifest is not None and read_manifest!=manifest:
            raise ContractError('factory-model-runtime-workspace')
        if ExecutionPolicy.from_dict(loaded['execution_policy']).to_dict()!=policy.to_dict():
            raise ContractError('factory-model-runtime-policy')
        return dict(admitted,workspace_read_manifest=dict(manifest))

    def private_expected_values(self, order, path, *, excluded_roots=(), now=None):
        """Load only an approved, bounded controller-private input; never log values."""
        import os
        import stat
        try:
            admitted = self.verify_plan(order, now=now)
            plan = self._committed_json(self.paths[0])
            if canonical_hash(plan, {'content_sha256'}) != admitted['plan_sha256']:
                raise ValueError('changed plan')
            binding = plan.get('private_expected_values', {})
            if (set(binding) != {'sha256', 'size_bytes', 'count'}
                    or not isinstance(binding['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', binding['sha256'])
                    or type(binding['size_bytes']) is not int
                    or not 1 <= binding['size_bytes'] <= 262144
                    or type(binding['count']) is not int or not 1 <= binding['count'] <= 64):
                raise ValueError('binding')
            candidate = Path(path)
            if not candidate.is_absolute():
                raise ValueError('absolute private path required')
            def checked_path():
                cursor = candidate
                while cursor != cursor.parent:
                    if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                        raise ValueError('private link')
                    cursor = cursor.parent
                resolved = candidate.resolve(strict=True)
                for root in (self.root, *excluded_roots):
                    root = Path(root).resolve()
                    if resolved == root or root in resolved.parents:
                        raise ValueError('private input in exposed root')
                metadata = resolved.stat()
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                        or metadata.st_size != binding['size_bytes']):
                    raise ValueError('private file metadata')
                return resolved, metadata
            resolved, metadata = checked_path()
            identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
            with resolved.open('rb') as stream:
                if identity(os.fstat(stream.fileno())) != identity(metadata):
                    raise ValueError('private input replaced')
                raw = stream.read(262145)
                if identity(os.fstat(stream.fileno())) != identity(metadata):
                    raise ValueError('private input changed')
            final_path, final_metadata = checked_path()
            if (final_path != resolved or identity(final_metadata) != identity(metadata)
                    or len(raw) != binding['size_bytes'] or sha256(raw).hexdigest() != binding['sha256']):
                raise ValueError('private input digest')
            bundle = json.loads(raw)
            if (not isinstance(bundle, dict) or set(bundle) != {'schema', 'values'}
                    or bundle['schema'] != 'factory-private-expected-values/1'
                    or not isinstance(bundle['values'], list) or len(bundle['values']) != binding['count']):
                raise ValueError('private input schema')
            values = bundle['values']
            if (any(not isinstance(v, str) or len(''.join(v.casefold().split())) < 40 for v in values)
                    or len(set(values)) != len(values)):
                raise ValueError('private input values')
            return tuple(values)
        except Exception:
            # Includes filesystem/JSON errors whose messages could contain private paths or values.
            raise ContractError('factory-private-expected-values-refused') from None

    def verify_plan(self, order, *, now=None):
        """Side-effect-free approval preflight before nonce or credential use.

        Provider identity is checked again at every actual call. This preflight
        alone is not permission to call a model or qualify a factory receipt.
        """
        return self._verify(order, None, None, now=now)

    def verify(self, order, provider, role, *, now=None):
        if provider is None:
            raise ContractError('factory-model-provider-required')
        return self._verify(order, provider, role, now=now)

    def _verify(self, order, provider, role, *, now=None):
        if subprocess.check_output(['git','--no-optional-locks','-C',str(self.root),
                                     'status','--porcelain=v1','--untracked-files=all']):
            raise ContractError('factory-model-dirty-executable')
        plan, proof, contract = [self._committed_json(path) for path in self.paths]
        digest = canonical_hash(plan, {'content_sha256'})
        if (plan.get('schema')!='factory-build-plan/1' or plan.get('content_sha256')!=digest
                or plan.get('work_order_sha256')!=order.content_sha256
                or contract.get('kind')!='engineering-run-approval'
                or contract.get('details', {}).get('request_seal')!=digest):
            raise ContractError('factory-model-plan-binding')
        details = contract['details']
        head = subprocess.check_output(['git','--no-optional-locks','-C',str(self.root),
                                        'rev-parse','HEAD']).decode().strip()
        executable=details.get('executable_commit')
        if (not isinstance(executable,str) or not re.fullmatch('[0-9a-f]{40}',executable)
                or plan.get('executable_commit')!=executable):
            raise ContractError('factory-model-executable-binding')
        subprocess.check_output(['git','--no-optional-locks','-C',str(self.root),
                                 'merge-base','--is-ancestor',executable,head])
        changed=subprocess.check_output(['git','--no-optional-locks','-C',str(self.root),
                                         'diff','--name-only','-z',executable,head]).decode().split('\0')
        if set(filter(None,changed))-set(self.paths):
            raise ContractError('factory-model-executable-changed')
        # Committing approval metadata may advance HEAD; executable bytes cannot.
        inputs=plan.get('bound_inputs', {})
        if set(inputs)!={'scope','freeze','workspace','execution_policy'}:
            raise ContractError('factory-model-input-bindings')
        sources={(row['path'],row['sha256']) for row in contract.get('sources',[])}
        if any(set(row)!={'path','sha256'} or not re.fullmatch('[0-9a-f]{64}',row.get('sha256',''))
               or (row['path'],row['sha256']) not in sources for row in inputs.values()):
            raise ContractError('factory-model-input-bindings')
        caps = plan.get('caps', {})
        if caps != details.get('caps') or any(type(value) is not int or value<=0 for value in caps.values()):
            raise ContractError('factory-model-caps-binding')
        expected = dict(max_attempts=order.max_attempts, max_elapsed_seconds=order.max_elapsed_seconds,
                        max_model_calls=order.max_model_calls, max_model_tokens=order.max_model_tokens)
        if (any(caps.get(k)!=v for k,v in expected.items()) or not 1<=caps['max_attempts']<=3
                or not 1<=caps.get('max_repair_loops',0)<=2
                or type(caps.get('cost_cap_microusd')) is not int
                or caps['cost_cap_microusd']/1000000 != order.max_model_cost_usd):
            raise ContractError('factory-model-order-caps')
        window = details['window']; start=datetime.fromisoformat(window['start']); end=datetime.fromisoformat(window['end'])
        current = now or datetime.now(timezone.utc)
        if start.tzinfo is None or end.tzinfo is None or current.tzinfo is None or not start<=current<end:
            raise ContractError('factory-model-window')
        roles=plan.get('roles', {})
        if set(roles)!={'planner','builder','analyst'}:
            raise ContractError('factory-model-role')
        for bound_provider in roles.values():
            if (not isinstance(bound_provider,dict) or set(bound_provider)!={'provider','model'}
                    or not isinstance(bound_provider['provider'],str) or not bound_provider['provider']):
                raise ContractError('factory-model-provider-binding')
            require_snapshot(bound_provider['model'])
        if provider is not None:
            role = 'analyst' if role=='failure_analyst' else role
            if role not in roles:
                raise ContractError('factory-model-role')
            require_snapshot(provider.model)
            if (roles[role] != {'provider':provider.provider_id,'model':provider.model}
                    or getattr(provider,'_injected_opener',False)):
                raise ContractError('factory-model-provider-binding')
        trusted = self.trusted_head()
        decision = FactoryDecisions(self.public_key, trusted, evidence_root=self.root).verify(
            proof, 'engineering-run-approval', contract, {'approve'})
        # Trust freshness is obtained out of band, never from the supplied proof.
        if self.trusted_head()!=trusted:
            raise ContractError('factory-model-trust-advanced')
        return dict(schema='factory-model-admission/1',plan_sha256=digest,
                    decision_sha256=proof['decision_sha256'],trusted_journal_head=trusted,
                    provider=provider.provider_id if provider is not None else None,
                    model=provider.model if provider is not None else None,role=role,
                    provider_verified=provider is not None,
                    executable_commit=head,work_order_sha256=order.content_sha256)
