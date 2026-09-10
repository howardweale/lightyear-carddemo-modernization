// CONFIG is supplied over stdin by the Python controller. It is never a file,
// command-line argument, environment variable, metric tag or console message.
import http from 'k6/http';
import encoding from 'k6/encoding';
import execution from 'k6/execution';
import { sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const operations = [
  'oauth', 'unauthenticated', 'customer', 'account', 'journals', 'transfer',
  'invalid_transfer', 'insufficient_transfer', 'deposit', 'clearance',
  'deposit_replay', 'clearance_replay', 'credit', 'chat',
];
const requests = new Counter('business_requests');
const errors = new Counter('business_errors');
const latency = new Trend('business_latency', true);
const cycles = new Counter('business_cycles');
const started = new Counter('business_cycles_started');
const effects = new Counter('checks_effects');
const checkLatency = new Trend('checks_delivery_latency', true);
const opCounts = {}, opLatency = {}, opErrors = {}, vuCycles = {}, replicas = {};
for (const op of operations) {
  opCounts[op] = new Counter('requests_' + op);
  opLatency[op] = new Trend('latency_' + op, true);
  opErrors[op] = new Counter('errors_' + op);
}
for (let i = 1; i <= CONFIG.vus; i++) vuCycles[i] = new Counter('cycles_vu_' + i);
for (const service of Object.keys(CONFIG.endpoints)) {
  for (let i = 0; i < 2; i++) replicas[service + '_' + i] = new Counter('replica_' + service.replace(/-/g, '_') + '_' + i);
}

export const options = {
  scenarios: { business: { executor: 'constant-vus', vus: CONFIG.vus,
    duration: CONFIG.duration_seconds + 's', gracefulStop: '120s' } },
  thresholds: {
    business_requests: ['count>=1000'], business_errors: ['count==0'],
    business_latency: ['p(95)<=500'], http_req_failed: ['rate==0'],
    business_cycles: ['count>=10'],
  },
  summaryTrendStats: ['count', 'min', 'max', 'avg', 'p(95)'],
  systemTags: ['status', 'method', 'name', 'scenario', 'expected_response'],
  maxRedirects: 0, discardResponseBodies: false,
  userAgent: 'LIGHTYEAR-MS67-bounded-load',
};

const tokens = {};
let currentOperation = 'oauth';
function reject() {
  errors.add(1);
  opErrors[currentOperation].add(1);
  execution.test.abort('load-business-contract-failed');
  throw new Error('load-business-contract-failed');
}
function must(value) { if (!value) reject(); }
function json(response) {
  try { return response.json(); } catch (_) { reject(); }
}
function call(op, service, method, path, role, body, statuses = [200], extra = {}) {
  const headers = { ...extra };
  if (role) headers.Authorization = 'Bearer ' + token(role);
  currentOperation = op;
  if (body !== undefined && typeof body !== 'string') {
    body = JSON.stringify(body);
    headers['Content-Type'] = 'application/json';
  }
  const replica = (__VU + __ITER) % 2;
  const response = http.request(method, CONFIG.endpoints[service][replica] + path, body, {
    headers, timeout: '45s', redirects: 0, tags: { name: op },
    responseCallback: http.expectedStatuses(...statuses),
  });
  requests.add(1);
  opCounts[op].add(1);
  replicas[service + '_' + replica].add(1);
  latency.add(response.timings.duration);
  opLatency[op].add(response.timings.duration);
  must(statuses.includes(response.status)
    && typeof response.body === 'string' && response.body.length <= 262144);
  return response;
}
function token(role) {
  const prior = tokens[role];
  if (prior && prior.exp > Date.now() / 1000 + 30) return prior.value;
  const credential = CONFIG.credentials[role];
  const body = 'grant_type=client_credentials&scope=' + encodeURIComponent(CONFIG.scopes[role]);
  const response = call('oauth', 'azn-server', 'POST', '/oauth2/token', null, body, [200], {
    Authorization: 'Basic ' + encoding.b64encode(credential[0] + ':' + credential[1]),
    'Content-Type': 'application/x-www-form-urlencoded',
  });
  const value = json(response);
  must(value && typeof value.access_token === 'string' && value.access_token.length <= 16384
    && String(value.token_type).toLowerCase() === 'bearer');
  let claims;
  try { claims = JSON.parse(encoding.b64decode(value.access_token.split('.')[1], 'rawurl', 's')); }
  catch (_) { reject(); }
  const granted = String(value.scope || '').split(' ').filter(Boolean).sort();
  const claimed = Array.isArray(claims.scope) ? [...claims.scope].sort() : String(claims.scope || '').split(' ').sort();
  must(JSON.stringify(granted) === JSON.stringify(claimed)
    && CONFIG.scopes[role].split(' ').every(scope => granted.includes(scope))
    && (role !== 'owner' || !granted.some(scope => ['cloudbank.internal', 'cloudbank.admin'].includes(scope)))
    && claims.sub === credential[0] && typeof claims.exp === 'number' && claims.exp > Date.now() / 1000 + 30);
  tokens[role] = { value: value.access_token, exp: claims.exp };
  return tokens[role].value;
}
function account(fixture, index) {
  const row = json(call('account', 'account', 'GET', '/api/v1/account/' + fixture.accounts[index], 'account'));
  must(row && row.accountId === fixture.accounts[index] && row.accountCustomerId === CONFIG.owner
    && row.accountOtherDetails === fixture.marker && Number.isSafeInteger(row.accountBalance));
  return row.accountBalance;
}
function journals(fixture, index) {
  const rows = json(call('journals', 'account', 'GET', '/api/v1/account/' + fixture.accounts[index] + '/journal', 'account'));
  must(Array.isArray(rows) && rows.length <= 200 && rows.every(row => row
    && row.accountId === fixture.accounts[index] && Number.isSafeInteger(row.journalId)
    && Number.isSafeInteger(row.journalAmount) && ['PENDING', 'DEPOSIT', 'WITHDRAW'].includes(row.journalType))
    && new Set(rows.map(row => row.journalId)).size === rows.length);
  return rows;
}
function transfer(fixture, from, to, amount, key, op, statuses = [200]) {
  call(op, 'transfer', 'POST', '/transfer?fromAccount=' + fixture.accounts[from]
    + '&toAccount=' + fixture.accounts[to] + '&amount=' + amount,
    'owner', undefined, statuses, { 'Idempotency-Key': key });
}
function delivered(fixture, id, kind) {
  const begin = Date.now();
  while (true) {
    const rows = journals(fixture, 0).filter(row => row.lraId === id);
    must(rows.length <= 1);
    if (rows.length === 1 && rows[0].journalType === kind) {
      must(rows[0].journalAmount === 1);
      checkLatency.add(Date.now() - begin);
      effects.add(1);
      return rows[0].journalId;
    }
    must(Date.now() - begin < 30000);
    sleep(0.5);
  }
}

export default function () {
  const begin = Date.now();
  const fixture = CONFIG.fixtures[__VU - 1];
  const key = 'ly-load-' + CONFIG.run_id + '-' + __VU + '-' + __ITER;
  errors.add(0);
  started.add(1);
  call('unauthenticated', 'customer', 'GET', '/api/v1/customer', null, undefined, [401]);
  const customer = json(call('customer', 'customer', 'GET', '/api/v1/customer/' + encodeURIComponent(CONFIG.owner), 'owner'));
  must(customer && customer.customerId === CONFIG.owner
    && customer.customerOtherDetails === 'lightyear-synthetic-journey-owner');
  must(JSON.stringify([0, 1, 2].map(i => account(fixture, i))) === '[1000,250,5]');
  transfer(fixture, 0, 1, 1, key + '-forward', 'transfer');
  must(account(fixture, 0) === 999 && account(fixture, 1) === 251);
  transfer(fixture, 1, 0, 1, key + '-back', 'transfer');
  transfer(fixture, 0, 1, 0, key + '-invalid', 'invalid_transfer', [400]);
  transfer(fixture, 2, 0, 6, key + '-insufficient', 'insufficient_transfer', [400, 409, 422]);

  const deposit = { accountId: fixture.accounts[0], amount: 1 };
  call('deposit', 'testrunner', 'POST', '/api/v1/testrunner/deposit', 'test', deposit, [201],
    { 'Idempotency-Key': key + '-deposit' });
  const journal = delivered(fixture, key + '-deposit', 'PENDING');
  call('clearance', 'testrunner', 'POST', '/api/v1/testrunner/clear', 'test', { journalId: journal }, [201],
    { 'Idempotency-Key': key + '-clear' });
  delivered(fixture, key + '-deposit', 'DEPOSIT');
  call('deposit_replay', 'testrunner', 'POST', '/api/v1/testrunner/deposit', 'test', deposit, [200],
    { 'Idempotency-Key': key + '-deposit' });
  call('clearance_replay', 'testrunner', 'POST', '/api/v1/testrunner/clear', 'test', { journalId: journal }, [200],
    { 'Idempotency-Key': key + '-clear' });

  const score = json(call('credit', 'creditscore', 'GET', '/api/v1/creditscore', 'credit'));
  must(score && /^[0-9]{3}$/.test(String(score['Credit Score']))
    && Number(score['Credit Score']) >= 500 && Number(score['Credit Score']) <= 899);
  const chat = call('chat', 'chatbot', 'POST', '/chat', 'chat', 'What is a checking account?', [200],
    { 'Content-Type': 'text/plain; charset=utf-8' }).body;
  must(chat.trim().length > 0 && chat.length <= 4000
    && !/(BEGIN (RSA )?PRIVATE KEY|authorization\s*:\s*bearer|(?:password|token|secret|api[_ -]?key)\s*[:=]\s*\S+)/i.test(chat));

  must(JSON.stringify([0, 1, 2].map(i => account(fixture, i))) === '[1000,250,5]');
  for (let i = 0; i < 3; i++) {
    const rows = journals(fixture, i), count = __ITER + 1;
    must(rows.length === count * [3, 2, 0][i]
      && rows.filter(r => r.journalType === 'WITHDRAW').length === (i < 2 ? count : 0)
      && rows.filter(r => r.journalType === 'DEPOSIT').length === count * [2, 1, 0][i]
      && rows.every(r => r.journalAmount === 1));
  }
  cycles.add(1);
  vuCycles[__VU].add(1);
  sleep(Math.max(0, CONFIG.cycle_seconds - (Date.now() - begin) / 1000));
}

export function handleSummary(data) {
  function values(name) { return data.metrics[name] ? data.metrics[name].values : {}; }
  function count(name) { return values(name).count || 0; }
  const byOperation = {}, byVu = {}, byReplica = {};
  for (const op of operations) byOperation[op] = {
    requests: count('requests_' + op), p95_ms: values('latency_' + op)['p(95)'] ?? null,
    latency_samples: count('latency_' + op), errors: count('errors_' + op),
  };
  for (let i = 1; i <= CONFIG.vus; i++) byVu[String(i)] = count('cycles_vu_' + i);
  for (const name of Object.keys(replicas)) byReplica[name] = count('replica_' + name.replace(/-/g, '_'));
  const result = {
    format: 'lightyear-k6-business-summary-v1', run_id: CONFIG.run_id,
    configured_duration_seconds: CONFIG.duration_seconds, configured_vus: CONFIG.vus,
    cycle_seconds: CONFIG.cycle_seconds, measured_duration_ms: data.state.testRunDurationMs,
    requests: count('business_requests'), errors: count('business_errors'),
    http_requests: count('http_reqs'), http_failures: values('http_req_failed').passes || 0,
    p95_ms: values('business_latency')['p(95)'] ?? null, latency_samples: count('business_latency'),
    cycles_started: count('business_cycles_started'), cycles_completed: count('business_cycles'),
    checks_effects: count('checks_effects'), checks_delivery_p95_ms: values('checks_delivery_latency')['p(95)'] ?? null,
    iterations: count('iterations'), vus_max: values('vus_max').max ?? null,
    operations: byOperation, vu_cycles: byVu, replica_requests: byReplica,
  };
  return { stdout: 'MS67_K6_SUMMARY=' + JSON.stringify(result) + '\n' };
}
