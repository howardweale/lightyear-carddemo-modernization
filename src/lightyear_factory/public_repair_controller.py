"""Graph-disabled five-repair controller. Trusted ports supply admission and IO.

No legacy INTCALC admission path is reused. This module never opens a socket,
loads a held-out case, grants authority, or invokes a graph tool.
"""
import hashlib
import json
import time

CAPS = {'planner': 112000, 'builder': 128000, 'analysis': 224000, 'repair': 240000}
HOLDS = {'planner': 2024000, 'builder': 2200000, 'analysis': 3256000, 'repair': 3432000}
MAX_RESERVATION = 37664000
CEILING = 37670000
WINDOW = 17520
MODEL = 'gpt-5.4-2026-03-05'
INSTRUCTIONS = {
    'planner': 'Plan the full public rewrite. Return only {"text": plain text}, at most 8192 UTF-8 bytes; no control characters except tab, LF, CR.',
    'builder': 'Write idiomatic Java; you may use the provided helper for decimal arithmetic and record encoding. Return only {"source": complete Main.java}, default-package Main, Java 21, pure JDK plus reviewed helper, not a patch. At most 65536 UTF-8 bytes; no control characters except tab, LF, CR.',
    'analysis': 'Analyze the best public candidate using the bounded public score history and current joined public feedback. Return only {"text": plain text}, at most 8192 UTF-8 bytes; no control characters except tab, LF, CR.',
    'repair': 'Repair the supplied candidate from the public score history, current joined public feedback and analysis. You may use the provided helper for decimal arithmetic and record encoding. Return only {"source": complete Main.java}, default-package Main, Java 21, pure JDK plus reviewed helper, not a patch. At most 65536 UTF-8 bytes; no control characters except tab, LF, CR.',
}
CODES = frozenset(('json-shape', 'binding-fields', 'binding-value', 'binding-hash',
    'public-context', 'context-cap', 'artifact-shape', 'artifact-text', 'artifact-cap',
    'component-cap', 'history-cap', 'envelope-cap', 'projection-cap', 'deadline',
    'reservation-cap', 'count-response', 'generation-response', 'usage-bound',
    'cost-bound', 'build-response', 'public-response', 'hidden-response',
    'feedback-shape', 'feedback-join', 'feedback-cap', 'feedback-row', 'feedback-diagnostic', 'model-closed', 'controller-reused', 'artifact-retention', 'port-fault'))


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def canonical(value):
    def validate(v):
        if type(v) in (str, int, bool) or v is None:
            return
        if type(v) is list:
            for item in v:
                validate(item)
        elif type(v) is dict and all(type(k) is str for k in v):
            for item in v.values():
                validate(item)
        else:
            raise Refused('json-shape')
    validate(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise Refused('json-shape') from exc


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


ROLE_HASH = digest(INSTRUCTIONS)


def hash_ok(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def shape(row, keys, code):
    require(type(row) is dict and set(row) == set(keys.split()), code)


def text_ok(value, raw_cap, encoded_cap):
    require(type(value) is str and not any(ord(c) < 32 and c not in '\t\n\r' for c in value),
            'artifact-text')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError as exc:
        raise Refused('artifact-text') from exc
    require(size <= raw_cap, 'artifact-cap')
    require(len(canonical(value)) <= encoded_cap, 'component-cap')
    return value


FIELDS = {'ACCTFILE': ['', 'ACCT-ACTIVE-STATUS', 'ACCT-ADDR-ZIP', 'ACCT-CASH-CREDIT-LIMIT', 'ACCT-CREDIT-LIMIT', 'ACCT-CURR-BAL', 'ACCT-CURR-CYC-CREDIT', 'ACCT-CURR-CYC-DEBIT', 'ACCT-EXPIRAION-DATE', 'ACCT-GROUP-ID', 'ACCT-ID', 'ACCT-OPEN-DATE', 'ACCT-REISSUE-DATE', 'FILLER'], 'TRANSACT': ['', 'FILLER', 'TRAN-AMT', 'TRAN-CARD-NUM', 'TRAN-CAT-CD', 'TRAN-DESC', 'TRAN-ID', 'TRAN-MERCHANT-CITY', 'TRAN-MERCHANT-ID', 'TRAN-MERCHANT-NAME', 'TRAN-MERCHANT-ZIP', 'TRAN-ORIG-TS', 'TRAN-PROC-TS', 'TRAN-SOURCE', 'TRAN-TYPE-CD'], 'stdout': [''], 'stderr': [''], 'exit': ['']}
FEEDBACK_POLICY = dict(schema='public-repair-feedback/1', fields=FIELDS,
    bytes_max=4096, rows_max=24, diagnostics_max=4, message_encoded_max=512)
FEEDBACK_HASH = digest(FEEDBACK_POLICY)


def validate_feedback(row, candidate, suite, kind):
    shape(row, 'schema candidate_sha256 public_suite_sha256 kind divergences diagnostics truncated',
          'feedback-shape')
    require(row['schema'] == 'public-repair-feedback/1' and row['kind'] == kind
            and kind in ('PUBLIC_DIVERGENCE', 'COMPILE_FAILED')
            and type(row['truncated']) is bool, 'feedback-shape')
    require(row['candidate_sha256'] == candidate and row['public_suite_sha256'] == suite
            and hash_ok(candidate) and hash_ok(suite), 'feedback-join')
    require(type(row['divergences']) is list and type(row['diagnostics']) is list,
            'feedback-shape')
    require(len(row['divergences']) <= 24 and len(row['diagnostics']) <= 4
            and len(canonical(row)) <= 4096, 'feedback-cap')
    require(not row['diagnostics'] if kind == 'PUBLIC_DIVERGENCE' else not row['divergences'],
            'feedback-shape')
    previous = None
    for item in row['divergences']:
        shape(item, 'channel field records_different records_compared', 'feedback-row')
        require(type(item['channel']) is str and item['channel'] in FIELDS
                and type(item['field']) is str and item['field'] in FIELDS[item['channel']],
                'feedback-row')
        a,b = item['records_different'],item['records_compared']
        require(type(a) is int and type(b) is int and 0 <= a <= b <= 9999999999,
                'feedback-row')
        order = (list(FIELDS).index(item['channel']), item['field'])
        require(previous is None or previous < order, 'feedback-row')
        previous = order
    previous = None
    for item in row['diagnostics']:
        shape(item, 'line column message', 'feedback-diagnostic')
        require(all(type(item[k]) is int and 0 <= item[k] <= 2147483647
                    for k in ('line','column')), 'feedback-diagnostic')
        message=item['message']
        require(type(message) is str and not any(ord(v)<32 and v not in '\t\n\r' for v in message)
                and len(canonical(message)) <= 512, 'feedback-diagnostic')
        order=(item['line'],item['column'],sha(message.encode('utf-8')))
        require(previous is None or previous <= order, 'feedback-diagnostic')
        previous=order
    # The independently qualified public/compiler adapter owns provenance and
    # diagnostic sanitizing. This boundary validates the closed, joined shape.
    return json.loads(canonical(row))


def validate_binding(row, context):
    shape(row, 'schema graph_mode max_repairs window_seconds cap_microdollars model service_tier output_cap retries authority_sha256 implementation_sha256 public_context_sha256 public_suite_sha256 heldout_commitment_sha256 runtime_profile_sha256 role_instructions_sha256 public_case_count feedback_contract_sha256', 'binding-fields')
    require(row['schema'] == 'public-repair-binding/1' and row['graph_mode'] == 'off'
            and type(row['max_repairs']) is int and row['max_repairs'] == 5
            and type(row['window_seconds']) is int and row['window_seconds'] == WINDOW
            and type(row['cap_microdollars']) is int and row['cap_microdollars'] == CEILING
            and row['model'] == MODEL and row['service_tier'] == 'flex'
            and type(row['output_cap']) is int and row['output_cap'] == 32000
            and type(row['retries']) is int and row['retries'] == 0
            and type(row['public_case_count']) is int and 1 <= row['public_case_count'] <= 9999999999,
            'binding-value')
    require(all(hash_ok(v) for k, v in row.items() if k.endswith('_sha256')), 'binding-hash')
    require(row['role_instructions_sha256'] == ROLE_HASH and row['feedback_contract_sha256'] == FEEDBACK_HASH, 'binding-hash')
    require(type(context) is dict and bool(context) and
            all(type(k) is str and type(v) is str for k, v in context.items()), 'public-context')
    require(len(canonical(context)) <= 98304, 'context-cap')
    require(digest(context) == row['public_context_sha256'], 'binding-hash')


def projection(role, context, plan, source, analysis, history, feedback=None):
    require(role in CAPS, 'projection-cap')
    row = dict(schema='public-repair-request/1', role=role, model=MODEL,
               service_tier='flex', max_output_tokens=32000, truncation='disabled',
               instructions=INSTRUCTIONS[role], public_context=context)
    if role != 'planner':
        row['plan'] = text_ok(plan, 8192, 16384)
    if role in ('analysis', 'repair'):
        row['source'] = text_ok(source, 65536, 73728)
        row['score_history'] = history
        require(type(feedback) is dict, 'feedback-shape')
        row['feedback'] = validate_feedback(feedback, sha(source.encode('utf-8')),
            feedback.get('public_suite_sha256'), feedback.get('kind'))
    if role == 'repair':
        row['analysis'] = text_ok(analysis, 8192, 16384)
    require(len(history) <= 6 and len(canonical({'score_history': history})) <= 1024, 'history-cap')
    components = ('public_context', 'plan', 'source', 'analysis', 'score_history', 'feedback')
    envelope = {k: v for k, v in row.items() if k not in components}
    # Separators and property names are charged by subtracting component values
    # from the actual full encoding, rather than estimating JSON overhead.
    residual = len(canonical(row)) - sum(len(canonical(row[k])) for k in components if k in row)
    require(residual <= 7168 and len(canonical(envelope)) <= 7168, 'envelope-cap')
    require(len(canonical(context)) <= 98304, 'context-cap')
    require(len(canonical(row)) + 4096 <= CAPS[role], 'projection-cap')
    return row


class Controller:
    """One-use state machine; ports are trusted, independently qualified adapters.

    Ports: admit(binding_bytes, deadline); record(name, public_record) exclusive
    and durable; count(request, deadline); generate(request, deadline);
    build(source, round, deadline); evaluate_public(build, suite_hash, deadline);
    retain_artifact(slot, key, text) -> readback SHA256; close_models();
    evaluate_hidden(selected, commitment_hash, deadline).
    No evaluator may expose hidden information to count/generate or public records.
    """
    def __init__(self, ports, binding, public_context, clock=time.monotonic):
        # Freeze caller-owned JSON before admission; later mutation cannot rebind.
        self.binding = json.loads(canonical(binding))
        self.context = json.loads(canonical(public_context))
        validate_binding(self.binding, self.context)
        self.ports = ports
        self.clock = clock
        self.used = False
        self.closed = False
        self.reserved = 0
        self.cost = 0
        self.history = []
        self.candidates = []
        self.best = None
        self.last_source = ''
        self.last_feedback = None
        self.binding_sha256 = digest(self.binding)
        self.stage = 'admission'

    def now_before(self, deadline):
        require(self.clock() < deadline, 'deadline')

    def record(self, name, row):
        canonical(row)  # never record float/provider content
        self.ports.record(name, row)

    def phase(self, seconds):
        self.now_before(self.end - 60)
        return min(self.clock() + seconds, self.end - 60)

    def close_models(self):
        if not self.closed:
            self.closed = True  # a failed close still forbids sends/hidden
            self.ports.close_models()

    def role(self, role, slot, plan='', source='', analysis='', feedback=None):
        require(not self.closed, 'model-closed')
        self.stage = slot
        if role in ('analysis', 'repair'):
            require(type(feedback) is dict, 'feedback-shape')
            feedback = validate_feedback(feedback, sha(source.encode('utf-8')),
                self.binding['public_suite_sha256'], feedback.get('kind'))
        request = projection(role, self.context, plan, source, analysis, list(self.history), feedback)
        self.now_before(self.end - 60)
        bound = len(canonical(request)) + 4096
        request_hash = digest(request)
        hold = HOLDS[role]
        require(self.reserved + hold <= MAX_RESERVATION <= self.binding['cap_microdollars'],
                'reservation-cap')
        self.reserved += hold
        self.record(slot+'-reservation', dict(role=role, request_sha256=request_hash,
            token_upper_bound=bound, hold_microdollars=hold, reserved_microdollars=self.reserved))
        phase_end = self.phase(1080)
        try:
            count_end = min(self.clock()+120, phase_end-960)
            self.now_before(count_end)
            self.record(slot+'-count-send', dict(request_sha256=request_hash))
            counted = self.ports.count(request, count_end)
            self.now_before(count_end)
            shape(counted, 'input_tokens request_sha256 receipt_sha256', 'count-response')
            require(counted['request_sha256'] == request_hash and hash_ok(counted['receipt_sha256'])
                    and type(counted['input_tokens']) is int and 0 <= counted['input_tokens'] <= bound,
                    'count-response')
            self.record(slot+'-count-response', counted)
            generation_end = min(self.clock()+900, phase_end-60)
            self.now_before(generation_end)
            self.record(slot+'-generation-send', dict(request_sha256=request_hash))
            result = self.ports.generate(request, generation_end)
            self.now_before(generation_end)
            shape(result, 'artifact input_tokens output_tokens model service_tier request_sha256 receipt_sha256',
                  'generation-response')
            require(result['request_sha256'] == request_hash and hash_ok(result['receipt_sha256'])
                    and result['model'] == MODEL and result['service_tier'] == 'flex',
                    'generation-response')
            require(type(result['input_tokens']) is int and 0 <= result['input_tokens'] <= bound
                    and type(result['output_tokens']) is int and 0 <= result['output_tokens'] <= 32000,
                    'usage-bound')
            # Ceil each request's charge separately; holds are never refunded.
            count_cost = (counted['input_tokens'] * 11 + 1) // 2
            generation_cost = (result['input_tokens'] * 22 + result['output_tokens'] * 99 + 3) // 4
            require(count_cost + generation_cost <= hold, 'cost-bound')
            self.cost += count_cost + generation_cost
            self.record(slot+'-generation-response', {k:v for k,v in result.items() if k != 'artifact'})
            key = 'source' if role in ('builder', 'repair') else 'text'
            shape(result['artifact'], key, 'artifact-shape')
            value = text_ok(result['artifact'][key], 65536 if key=='source' else 8192,
                            73728 if key=='source' else 16384)
            require(self.ports.retain_artifact(slot, key, value) == sha(value.encode('utf-8')),
                    'artifact-retention')
            self.now_before(phase_end)
            self.record(slot+'-complete', dict(artifact_sha256=sha(value.encode('utf-8')),
                bytes=len(value.encode('utf-8')), counted_input_tokens=counted['input_tokens'],
                usage_input_tokens=result['input_tokens'],
                count_usage_match=counted['input_tokens']==result['input_tokens'],
                accounted_microdollars=count_cost+generation_cost, billing_final=False))
            return value
        except BaseException as exc:
            self.failure(slot+'-failed', exc)
            raise

    def failure(self, name, error):
        code = str(error) if isinstance(error, Refused) and str(error) in CODES else 'port-fault'
        try:
            self.record(name, dict(failure_schema='public-repair-failure/1', refusal_code=code,
                                  stage=self.stage))
        except BaseException:
            pass  # original failure is never masked

    def candidate(self, source, round_no):
        deadline = self.phase(600)
        identity = sha(source.encode('utf-8'))
        self.last_source = source
        self.stage = 'build-'+str(round_no)
        built = self.ports.build(source, round_no, deadline)
        self.now_before(deadline)
        shape(built, 'status artifact_sha256 build_receipt_sha256 cleanup feedback', 'build-response')
        require(built['status'] in ('BUILT', 'COMPILE_FAILED') and built['cleanup'] is True
                and built['artifact_sha256'] == identity and hash_ok(built['build_receipt_sha256']),
                'build-response')
        score = dict(round=round_no, candidate=identity[:16], match=None, different=None)
        item = dict(round=round_no, artifact_sha256=identity,
                    build_receipt_sha256=built['build_receipt_sha256'], status=built['status'])
        if built['status'] == 'BUILT':
            require(built['feedback'] is None, 'build-response')
            self.stage = 'public-'+str(round_no)
            result = self.ports.evaluate_public(built, self.binding['public_suite_sha256'], deadline)
            self.now_before(deadline)
            shape(result, 'suite_sha256 artifact_sha256 build_receipt_sha256 match different total complete cleanup receipt_sha256 feedback',
                  'public-response')
            require(result['suite_sha256'] == self.binding['public_suite_sha256']
                    and result['artifact_sha256'] == identity
                    and result['build_receipt_sha256'] == built['build_receipt_sha256']
                    and hash_ok(result['receipt_sha256']) and result['complete'] is True
                    and result['cleanup'] is True and all(type(result[k]) is int and result[k]>=0
                        for k in ('match','different','total'))
                    and result['match']+result['different']==result['total']==self.binding['public_case_count'],
                    'public-response')
            feedback = validate_feedback(result['feedback'], identity,
                self.binding['public_suite_sha256'], 'PUBLIC_DIVERGENCE')
            score.update(match=result['match'], different=result['different'])
            item.update(match=result['match'], different=result['different'],
                        public_receipt_sha256=result['receipt_sha256'],
                        feedback_sha256=digest(feedback))
            if self.best is None or item['match'] >= self.best['match']:
                self.best = dict(item, source=source, feedback=feedback)
        else:
            feedback = validate_feedback(built['feedback'], identity,
                self.binding['public_suite_sha256'], 'COMPILE_FAILED')
        self.last_feedback = feedback
        item['feedback_sha256'] = digest(feedback)
        self.record('public-feedback-'+str(round_no), feedback)
        self.history.append(score)
        self.candidates.append(item)
        self.record('attempt-'+str(round_no), item)
        return score['different'] == 0

    def run(self):
        require(not self.used, 'controller-reused')
        self.used = True
        self.start = self.clock()
        self.end = self.start + WINDOW
        admitted = False
        try:
            admission = self.ports.admit(canonical(self.binding), self.start + 300)
            self.now_before(self.start + 300)
            shape(admission, 'binding_sha256 receipt_sha256', 'binding-hash')
            require(admission['binding_sha256'] == self.binding_sha256
                    and hash_ok(admission['receipt_sha256']), 'binding-hash')
            admitted = True
            self.record('admitted', dict(binding_sha256=self.binding_sha256,
                graph_mode='off', maximum_repairs=5, window_seconds=WINDOW, cap_microdollars=CEILING,
                admission_receipt_sha256=admission['receipt_sha256']))
            plan = self.role('planner', 'planner')
            source = self.role('builder', 'builder-0', plan=plan)
            complete = self.candidate(source, 0)
            for round_no in range(1, 6):
                if complete:
                    break
                current = self.best['source'] if self.best is not None else self.last_source
                feedback = self.best['feedback'] if self.best is not None else self.last_feedback
                analysis = self.role('analysis', 'analysis-'+str(round_no), plan, current, feedback=feedback)
                source = self.role('repair', 'repair-'+str(round_no), plan, current, analysis, feedback)
                complete = self.candidate(source, round_no)
            selected = None if self.best is None else {k:v for k,v in self.best.items() if k not in ('source','feedback')}
            self.record('selection', dict(rule='maximum-public-match-ties-latest',
                selected=selected, evaluated_candidates=self.candidates))
            self.close_models()  # no model call after hidden boundary
            hidden = dict(status='NOT_RUN', reason='no-evaluated-candidate')
            status = 'CANDIDATE_FAIL'
            if selected is not None and selected['different'] > 0:
                hidden = dict(status='NOT_RUN', reason='public-fail')
                status = 'PUBLIC_FAIL'
            elif selected is not None:
                # Exclusive invocation record consumes the single hidden allowance.
                self.record('hidden-invocation', dict(selected=selected,
                    heldout_commitment_sha256=self.binding['heldout_commitment_sha256']))
                deadline = self.phase(600)
                self.stage = 'hidden-final'
                hidden = self.ports.evaluate_hidden(selected, self.binding['heldout_commitment_sha256'], deadline)
                self.now_before(deadline)
                shape(hidden, 'status receipt_sha256 cleanup', 'hidden-response')
                require(hidden['status'] in ('PASS','FAIL') and hash_ok(hidden['receipt_sha256'])
                        and hidden['cleanup'] is True, 'hidden-response')
                status = 'CANDIDATE_PASS' if hidden['status']=='PASS' else 'CANDIDATE_FAIL'
            self.now_before(self.end)
            result = dict(schema='public-repair-result/1', status=status, graph_mode='off',
                binding_sha256=self.binding_sha256, selected=selected, score_history=self.history,
                hidden=hidden, reserved_microdollars=self.reserved,
                accounted_microdollars=self.cost, billing_final=False, qualified=False)
            self.record('result', result)
            return result
        except BaseException as exc:
            if admitted:
                self.failure('stopped', exc)
            raise
        finally:
            # Closing cannot turn a stopped run into a retry or hide its original fault.
            if not self.closed:
                try:
                    self.close_models()
                except BaseException:
                    pass
