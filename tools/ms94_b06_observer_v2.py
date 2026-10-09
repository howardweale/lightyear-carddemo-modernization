"""Prospective native observer-v2 replay. No name-based or synthetic trust.

The manifest is a plan-bound private input. The broker authenticates the external
JDI stream and independently hashes runtime files; this module verifies content.
Historical streams continue through their original replay implementation.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from tools.ms94_b06_admission import bound_file, check
from tools.ms94_b06_classfile import inspect_class
from tools.b06_host_probe.pool_analysis import method_flags
from tools.b06_host_probe.generation_replay import (
    declared_definition, lambda_linkage, lambda_body, adjacent_target, class_file,
)
from tools.b06_host_probe.lambda_form_replay import (
    Graph, emission_definition_binding, class_data_initialization, replay_body,
    observed_dynamic_target,
)

POLICY = 'observer-binding-v2'
AMENDMENT = 'a6ae76dee979c59badeec20630b54e83dbcaddc85d8467ff3d4e1adb9d4b8898'
POOL_APPROVAL = '92c06471136b65106bec9fcb6ec41e12b18426e515c6a53d15c1aaad25fb1ce7'
FACTORY = 'java.lang.invoke.InnerClassLambdaMetafactory'
DEFINER = 'java.lang.invoke.MethodHandles$Lookup$ClassDefiner'
INVOKER = 'java.lang.invoke.InvokerBytecodeGenerator'
LOADER = 'java.lang.ClassLoader'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_manifest(root, spec, image):
    ref = spec['observer_binding_v2']
    check(set(ref) == {'policy', 'path', 'sha256'} and ref['policy'] == POLICY,
          'observer-v2-policy')
    check(spec.get('forwarding_stub') is None, 'observer-v2-legacy-policy-parallel')
    raw = bound_file(root, ref['path'], ref['sha256']).read_bytes()
    manifest = json.loads(raw)
    check(manifest['schema'] == 'b06-observer-bindings/2' and
          manifest['amendment_sha256'] == AMENDMENT and
          manifest['pool_approval_sha256'] == POOL_APPROVAL and
          manifest['image'] == image, 'observer-v2-manifest-authority')
    files = manifest['runtime_files']
    jdk = manifest['jdk']
    jdk_root = PurePosixPath(jdk['java']).parent.parent
    check(jdk['modules'] == str(jdk_root / 'lib/modules') and jdk['release'] == str(jdk_root / 'release') and
          {str(jdk_root / 'lib/server/libjvm.so'), str(jdk_root / 'lib/libjava.so')} <= set(jdk['native_providers']),
          'observer-v2-jdk-runtime-closure')
    check(spec.get('expected_jvm_arguments'), 'observer-v2-exact-launch-required')
    check(files.get(jdk['java']) == spec['java_binary_sha256'] and
          jdk['modules'] in files and jdk['release'] in files and jdk['native_providers'] and
          all(p in files for p in jdk['native_providers']), 'observer-v2-jdk-provider-closure')
    check(all(p.startswith('/') and '..' not in p.split('/') and
              len(h) == 64 and all(c in '0123456789abcdef' for c in h)
              for p, h in files.items()), 'observer-v2-runtime-files')
    entries = []
    identities = set()
    archive_bytes = {}
    zip_cache = {}
    for row in manifest['classes']:
        data = bound_file(root, row['path'], row['sha256']).read_bytes()
        info = inspect_class(data)
        check(info['class'] == row['class'] and row['kind'] in ('jdk', 'ordinary'),
              'observer-v2-class-input')
        identity = (row['class'], row['origin'], tuple(row['members']))
        check(identity not in identities, 'observer-v2-duplicate-origin')
        identities.add(identity)
        check(row['origin'] in files, 'observer-v2-unmeasured-origin')
        if row['kind'] == 'jdk':
            check(row['origin'] == jdk['modules'] and row['module'] and
                  row['members'] == [row['module'] + '/' + row['class'].replace('.', '/') + '.class'],
                  'observer-v2-module-entry')
        elif row['members']:
            import io, zipfile
            archive_key = (row['archive_path'], files[row['origin']])
            if archive_key not in archive_bytes:
                archive_bytes[archive_key] = bound_file(root, *archive_key).read_bytes()
            body = archive_bytes[archive_key]; chain = archive_key
            for member in row['members']:
                if chain not in zip_cache:
                    jar = zipfile.ZipFile(io.BytesIO(body))
                    from collections import Counter
                    zip_cache[chain] = (jar, Counter(jar.namelist()))
                jar, counts = zip_cache[chain]
                check(counts[member] == 1, 'observer-v2-jar-member-ambiguous')
                body = jar.read(member); chain = (*chain, member)
            check(body == data, 'observer-v2-jar-entry-differs')
        else:
            check(files[row['origin']] == row['sha256'], 'observer-v2-loose-class-differs')
        if row.get('native_provider') is not None:
            check(row['native_provider'] in jdk['native_providers'], 'observer-v2-native-provider-not-approved')
        entries.append({**row, 'bytes': data, 'methods': info['methods']})
    for jar, _ in zip_cache.values(): jar.close()
    check(entries, 'observer-v2-empty-manifest')
    return manifest, entries


def code_source(record):
    url = record.get('code_source')
    check(isinstance(url, dict) and url.get('protocol') == 'file' and
          url.get('host') in ('', None) and str(url.get('port')) == '-1',
          'observer-v2-code-source-unresolved')
    return unquote(url['file'])


class Replay:
    def __init__(self, entries):
        self.entries = entries
        self.definitions = {}
        self.pending = {}
        self.ordinary = {}
        self.factories = {}
        self.definers = {}
        self.emissions = {}
        self.bound = {}
        self.bound_identities = set()
        self.selected = {}
        self.frame_count = 0
        self.generated_proofs = []
        self.dispatch_definitions = set()
        self.captured_fields = set()

    def event(self, event):
        kind = event['kind']
        if kind == 'class-definition-v2':
            d = event['definition']; key = str(d['class_object_id'])
            old = self.definitions.get(key)
            check(old is None or all(old.get(k) == d.get(k) for k in ('class', 'loader', 'class_object_id')),
                  'observer-v2-class-identity-rewritten')
            self.bound.clear(); self.selected.clear()
            self.dispatch_definitions.clear(); self.captured_fields.clear()
            self.definitions[key] = d
            return True
        if kind not in ('generation-entry', 'generation-return', 'generation-unwind'):
            return False
        r = event['record']; stack = self.pending.setdefault(r['thread_id'], [])
        if kind == 'generation-entry':
            stack.append(r)
            return True
        check(stack, 'observer-v2-return-without-entry')
        entry = stack.pop()
        check(all(r.get(k) == v for k, v in entry.items()), 'observer-v2-return-binding')
        if kind == 'generation-unwind':
            check(event['catch_depth'] < r['entry_depth'] and event['exception_class'],
                  'observer-v2-unwind-depth')
            return True
        if r['entry_method'].startswith(INVOKER + '.'):
            key = (r['thread_id'], r['returned_bytes_object_id'])
            check(key not in self.emissions, 'observer-v2-emission-reused')
            self.emissions[key] = r
        else:
            key = str(r['returned_class']['class_object_id'])
            table = (self.ordinary if r['entry_method'].startswith(LOADER + '.') else
                     self.factories if r['entry_method'].startswith(FACTORY + '.') else self.definers)
            # A cached factory return may repeat, but must return the same Class
            # from the same byte-bound host/site. Every invocation is retained.
            if key in table:
                check(table is self.factories and table[key]['lambda_factory'] == r['lambda_factory'],
                      'observer-v2-returned-class-redefined')
            table[key] = r
        return True

    def ordinary_binding(self, identity):
        identity = str(identity)
        if identity in self.bound:
            return self.bound[identity]
        d = self.definitions[identity]
        check('/' not in d['class'] and identity not in self.definers and identity not in self.factories,
              'observer-v2-generated-not-ordinary')
        choices = [r for r in self.entries if r['class'] == d['class']]
        if d.get('module') and d.get('module_loader') == d['loader'] and (
                d['loader'] == 'bootstrap' or
                d.get('loader_class') == 'jdk.internal.loader.ClassLoaders$PlatformClassLoader'):
            choices = [r for r in choices if r['kind'] == 'jdk' and r['module'] == d['module']]
            check(len(choices) == 1, 'observer-v2-jdk-origin-ambiguous')
            row = choices[0]
            if d['loader'] != 'bootstrap':
                loader_id = str(d.get('loader_class_object_id'))
                check(loader_id != identity, 'observer-v2-platform-loader-cycle')
                loader = self.ordinary_binding(loader_id)
                check(loader['kind'] == 'jdk' and loader['loader'] == 'bootstrap' and
                      loader['class'] == 'jdk.internal.loader.ClassLoaders$PlatformClassLoader',
                      'observer-v2-platform-loader-not-bound')
            declared_definition(row['bytes'], d)
            # Genuine ordinary boot/platform definitions are trusted through the
            # measured module/provider files and exact untransformed JVM launch.
            # Generated classes never take this path, even in java.base.
            check(d.get('module_id') is not None, 'observer-v2-module-identity-missing')
        else:
            r = self.ordinary.get(identity)
            check(r is not None and r['entry_method'] == LOADER +
                  '.defineClass(Ljava/lang/String;[BIILjava/security/ProtectionDomain;)Ljava/lang/Class;',
                  'observer-v2-ordinary-definition-missing')
            self.generator(r, LOADER)
            raw = bytes.fromhex(r['definition_input_hex'])
            check(sha(raw) == r['definition_input_sha256'] and
                  r['returned_class']['class'] == d['class'] and
                  r['returned_class']['loader'] == r['defining_loader'] == d['loader'] and
                  r['requested_name'] in (None, d['class']), 'observer-v2-definition-origin')
            source = code_source(r)
            choices = [x for x in choices if x['kind'] == 'ordinary' and
                       x['code_source'] == source and x['bytes'] == raw]
            check(len(choices) == 1, 'observer-v2-artifact-origin-ambiguous')
            row = choices[0]
            check(d['loader_class'] == row['loader_class'], 'observer-v2-defining-loader-class')
            # The loader class is itself a byte-bound JDK or ordinary definition.
            # A candidate-created namesake class loader supplies no authority.
            loader_id = str(d['loader_class_object_id'])
            check(loader_id != identity, 'observer-v2-loader-cycle')
            self.ordinary_binding(loader_id)
            engines = [x['bytes'] for x in self.entries if x['class'] == 'org.junit.platform.engine.TestEngine']
            check(len(set(engines)) <= 1, 'observer-v2-engine-interface-ambiguous')
            declared_definition(raw, d, engines[0] if engines else None)
        result = {'class': d['class'], 'loader': d['loader'], 'class_sha256': row['sha256'],
                  'methods': row['methods'], 'method_flags': method_flags(row['bytes']),
                  'kind': row['kind'], 'origin': row['origin']}
        self.bound_identities.add(identity)
        self.bound[identity] = result; self.selected[identity] = row
        return result

    def generator(self, record, expected):
        top = record['stack'][0]
        check(top['class'] == expected and record['entry_method'] ==
              top['class'] + '.' + top['method'] + top['signature'], 'observer-v2-generator-frame')
        bound = self.ordinary_binding(top['class_object_id'])
        check(bound['kind'] == 'jdk' and bound['class'] == expected,
              'observer-v2-generator-not-pinned-jdk')
        key = top['method'] + top['signature']
        check(key in bound['methods'] and top['code_index'] == 0, 'observer-v2-generator-method')
        d = self.definitions[str(top['class_object_id'])]
        methods = [m for m in d['methods'] if m['name'] + m['signature'] == key]
        check(len(methods) == 1 and sha(bytes.fromhex(methods[0]['bytecode_hex'])) ==
              methods[0]['sha256'] == bound['methods'][key], 'observer-v2-generator-bytecode')

    def frame(self, frame):
        d = self.definitions[str(frame['class_object_id'])]
        check(all(frame[k] == d[k] for k in ('class', 'loader')),
              'observer-v2-frame-class-identity')
        methods = [m for m in d['methods'] if (m['name'], m['signature']) == (frame['method'], frame['signature'])]
        check(len(methods) == 1, 'observer-v2-frame-method-missing')
        m = methods[0]
        code = bytes.fromhex(m.get('bytecode_hex', ''))
        unavailable = bool(m['modifiers'] & (0x100 | 0x400))
        check((not unavailable and sha(code) == m['sha256'] == frame['method_sha256']) or
              (unavailable and not code and frame['method_sha256'] == 'unavailable'),
              'observer-v2-frame-bytecode')
        check(sha(bytes.fromhex(d['constant_pool_hex'])) == d['constant_pool_sha256'] ==
              frame['constant_pool_sha256'], 'observer-v2-frame-pool')
        return d

    def frames(self, frames):
        check(frames, 'observer-v2-empty-stack')
        result = [dict(f) for f in frames]
        for f in result:
            f.pop('_verified_forwarding_host', None)
            self.frame(f)
            if '/' not in f['class'] and str(f['class_object_id']) not in self.definers and str(f['class_object_id']) not in self.factories:
                bound = self.ordinary_binding(f['class_object_id'])
                m = next(m for m in self.definitions[str(f['class_object_id'])]['methods']
                         if (m['name'],m['signature']) == (f['method'],f['signature']))
                expected_flags = bound['method_flags'].get(f['method'] + f['signature'])
                if expected_flags is not None and expected_flags & 0x1000:
                    expected_flags = (expected_flags | 0xf0000000) - (1 << 32)
                check(m['modifiers'] == expected_flags, 'observer-v2-executed-method-flags')
                check(not m['modifiers'] & 0x400, 'observer-v2-executing-abstract-method')
                if m['modifiers'] & 0x100 and bound['kind'] != 'jdk':
                    check(self.selected[str(f['class_object_id'])].get('native_provider') is not None,
                          'observer-v2-native-provider-missing')
                check(bound['methods'].get(f['method'] + f['signature']) == f['method_sha256'],
                      'observer-v2-bound-executed-method')
        for i, f in enumerate(result):
            if '/' not in f['class'] and str(f['class_object_id']) not in self.definers and str(f['class_object_id']) not in self.factories:
                continue
            identity = str(f['class_object_id']); d = self.definitions[identity]
            if identity in self.factories:
                r = self.factories[identity]; self.generator(r, FACTORY)
                host = r['lambda_factory']['targetClass']
                self.ordinary_binding(host['class_object_id'])
                raw = self.selected[str(host['class_object_id'])]['bytes']
                interfaces = {x['bytes'] for x in self.entries if x['class'] == 'org.junit.platform.engine.TestEngine'}
                check(len(interfaces) <= 1, 'observer-v2-engine-interface-ambiguous')
                proof = lambda_linkage(r, self.definitions, raw, test_engine=next(iter(interfaces), None))
                lambda_body(r, self.definitions, proof)
                adjacent_target(proof, result)
                f['_verified_forwarding_host'] = host['class']
                self.generated_proofs.append({'class_object_id': identity, 'kind': 'lambda',
                                             'host': host['class'], 'target': proof['implementation']})
            else:
                self.form(i, result, d)
        self.frame_count += len(frames)
        return result

    def form_definition(self, identity):
        identity = str(identity)
        if identity in self.dispatch_definitions:
            return
        runtime = self.definitions[identity]
        check(identity in self.definers, 'observer-v2-generated-provenance-missing')
        definition = self.definers[identity]
        emission = self.emissions.get((definition['thread_id'], definition.get('definition_input_object_id')))
        check(emission is not None, 'observer-v2-form-emission-missing')
        self.generator(definition, DEFINER); self.generator(emission, INVOKER)
        emission_definition_binding(emission, definition, runtime)
        class_data_initialization(definition)
        for method in runtime['methods']:
            if method['name'] != '<clinit>':
                replay_body(runtime, definition['lambda_form_graph'], method['name'])
        self.dispatch_definitions.add(identity)

    def captured_field(self, klass, member):
        """Read-only captured-data layout, never an executable-frame admission.

        A MethodHandle can store its captures in a generated species object.
        Reading its final instance field grants no trust to its constructor,
        initializer or methods. Those remain subject to ordinary/frame policy.
        """
        kind, owner, name, desc = member; identity = str(klass['class_object_id'])
        check(kind == 1 and identity in self.definers, 'observer-v2-capture-not-instance-read')
        record = self.definers[identity]; runtime = self.definitions[identity]
        self.generator(record, DEFINER)
        returned = record['returned_class']; raw = bytes.fromhex(record['definition_input_hex'])
        check(returned['class_object_id'] == runtime['class_object_id'] and
              returned['class'] == owner == runtime['class'] and
              returned['loader'] == klass['loader'] == runtime['loader'] and
              sha(raw) == record['definition_input_sha256'], 'observer-v2-capture-class-binding')
        cls = declared_definition(raw, runtime)
        field = cls['fields'].get(name + desc)
        check(field is not None and field['flags'] & 0x10 and not field['flags'] & 8,
              'observer-v2-capture-field-not-final-instance')
        expected = {(f['name'],f['signature'],f['flags']) for f in cls['fields'].values()}
        check(expected == {(f['name'],f['signature'],f['modifiers']) for f in runtime['fields']},
              'observer-v2-capture-layout-differs')
        self.captured_fields.add((identity, owner, name, desc))

    def form(self, index, frames, runtime):
        identity = str(runtime['class_object_id'])
        self.form_definition(identity)
        # Every captured handle belongs to this suspended frame. Follow ALL
        # reachable MemberNames; never pick a graph because it happens to match.
        uses = frames[index].get('handle_uses', [])
        check(uses and len({u['value_index'] for u in uses}) == len(uses), 'observer-v2-use-handle-missing')
        targets = []
        for use in uses:
            graph = Graph(use['handle_graph']); todo = [graph.root]; seen = set(); external = False
            while todo:
                ref = todo.pop()
                if ref in seen: continue
                seen.add(ref); node = graph.node(ref)
                todo.extend(v['ref'] for v in node.get('fields', {}).values()
                            if isinstance(v, dict) and set(v) == {'ref'})
                if node['class'] != 'java.lang.invoke.MemberName': continue
                klass = graph.value(node['fields']['java.lang.invoke.MemberName.clazz'])
                member_id = str(klass['class_object_id'])
                if member_id in self.definers and graph.member(ref)[0] == 1:
                    self.captured_field(klass, graph.member(ref))
                    continue
                if member_id in self.definers:
                    self.form_definition(member_id)
                    generated = self.definitions[member_id]
                    kind, owner, name, desc = graph.member(ref)
                    check(owner == generated['class'] and klass['loader'] == generated['loader'] and
                          kind in (5,6,7,9) and any(m['name'] == name and m['signature'] == desc
                          for m in generated['methods']), 'observer-v2-generated-use-member')
                    continue
                bound = self.ordinary_binding(member_id)
                # Resolve even the JDK members; an opaque name/type cannot be
                # silently discarded merely because its holder is java.base.
                kind, owner, name, desc = graph.member(ref)
                check(owner == bound['class'] and kind in (1,2,3,4,5,6,7,8,9), 'observer-v2-use-member')
                external |= bound['kind'] != 'jdk'
            if external:
                proof = observed_dynamic_target(use['handle_graph'], frames[:index], self.definitions,
                    self.bound, {k for k, v in self.bound.items() if v['kind'] == 'jdk'},
                    generated_dispatch_ids=self.dispatch_definitions, captured_fields=self.captured_fields)
                targets.append(proof)
        check(targets and len({json.dumps(p['actual_target'], sort_keys=True) for p in targets}) == 1,
              'observer-v2-use-target-missing-or-ambiguous')
        target = targets[0]['actual_target']
        positions = [i for i, f in enumerate(frames[:index]) if str(f['class_object_id']) == target['class_object_id'] and
                     (f['method'], f['signature']) == (target['method'], target['signature'])]
        check(len(positions) == 1, 'observer-v2-use-target-position')
        # Intervening frames must be independently bound JDK adapters or hidden
        # adapters checked by this same loop, not an arbitrary helper.
        check(all('/' in f['class'] or self.bound[str(f['class_object_id'])]['kind'] == 'jdk'
                  for f in frames[positions[0]+1:index]), 'observer-v2-use-untrusted-intermediate')
        frames[index]['_verified_forwarding_host'] = target['class']
        self.generated_proofs.append({'class_object_id': identity, 'kind': 'lambda-form',
                                     'target': target, 'use_bound': True})

    def finish(self):
        check(not any(self.pending.values()), 'observer-v2-open-generation')
        return {'policy': POLICY, 'frames_verified': self.frame_count,
                'generated_proofs': self.generated_proofs,
                'bound_class_count': len(self.bound_identities), 'captured_data_fields': sorted(self.captured_fields),
                'native_qualification': False}


def commitments(records):
    return [{'sequence': r['event']['sequence'], 'kind': r['event']['kind'],
             'event_sha256': r['content_sha256']} for r in records
            if r['event']['kind'] in ('class-definition-v2', 'generation-entry',
                                     'generation-return', 'generation-unwind') or
            r['event'].get('frames')]
