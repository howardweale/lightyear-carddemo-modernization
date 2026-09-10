#!/usr/bin/env python3
"""Restart the materialized Customer application against isolated PostgreSQL.

CI only: reproduce fixture resets with Liquibase enabled, then prove that the
same application with LIQUIBASE_ENABLED=false preserves edited and added rows.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lightyear_data.cloudbank_ms67_drills import CUSTOMER_MIGRATIONS_SQL, detailed_snapshot, snapshot_difference
from lightyear_data.cloudbank_sql_recovery import SNAPSHOT_SQL


def command(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=180, **kw).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, required=True)
    args = parser.parse_args()
    jar = args.jar.resolve()
    assert jar.is_file()
    name = 'ms67-customer-startup-' + uuid.uuid4().hex[:12]
    try:
        command(['docker', 'run', '-d', '--name', name, '-p', '127.0.0.1::5432',
                 '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:16-alpine'])
        port = json.loads(command(['docker', 'inspect', name]))[0]['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort']
        deadline = time.monotonic() + 60
        while subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres'], capture_output=True).returncode:
            assert time.monotonic() < deadline, 'PostgreSQL did not become ready'
            time.sleep(1)
        def query(sql):
            return command(['docker', 'exec', '-i', name, 'psql', '-U', 'postgres', '-d', 'postgres',
                            '-X', '-qAt', '--set=ON_ERROR_STOP=1'], input=sql)
        def snapshot(): return detailed_snapshot(query(SNAPSHOT_SQL))
        with tempfile.TemporaryDirectory(prefix='ms67-customer-startup-') as directory:
            def restart(enabled):
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); http_port = sock.getsockname()[1]
                env = {**os.environ, 'SERVER_ADDRESS': '127.0.0.1', 'SERVER_PORT': str(http_port),
                       'SPRING_DATASOURCE_URL': f'jdbc:postgresql://127.0.0.1:{port}/postgres',
                       'SPRING_DATASOURCE_USERNAME': 'postgres', 'SPRING_DATASOURCE_PASSWORD': '',
                       'SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT': 'org.hibernate.dialect.PostgreSQLDialect',
                       'LIQUIBASE_ENABLED': str(enabled).lower(), 'EUREKA_CLIENT_ENABLED': 'false',
                       'SPRING_CLOUD_CONFIG_ENABLED': 'false', 'SPRING_CLOUD_DISCOVERY_ENABLED': 'false',
                       'MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED': 'true',
                       'CLOUDBANK_SECURITY_ISSUER_URI': 'http://127.0.0.1:9',
                       'CLOUDBANK_OAUTH_ISSUER': 'http://127.0.0.1:9',
                       'CLOUDBANK_OAUTH_JWK_SET_URI': 'http://127.0.0.1:9/oauth2/jwks',
                       'SPRING_SECURITY_OAUTH2_RESOURCESERVER_JWT_JWK_SET_URI': 'http://127.0.0.1:9/oauth2/jwks',
                       'CLOUDBANK_SECURITY_JWK_SET_URI': 'http://127.0.0.1:9/oauth2/jwks'}
                log = Path(directory) / 'customer.log'
                with log.open('w') as stream:
                    process = subprocess.Popen(['java', '-jar', str(jar)], env=env, stdout=stream, stderr=subprocess.STDOUT)
                    try:
                        deadline = time.monotonic() + 90
                        while True:
                            assert process.poll() is None, log.read_text()
                            try:
                                with urlopen(f'http://127.0.0.1:{http_port}/actuator/health/readiness', timeout=2) as response:
                                    if response.status == 200: break
                            except (URLError, OSError): pass
                            assert time.monotonic() < deadline, log.read_text()
                            time.sleep(.5)
                    finally:
                        process.terminate()
                        try: process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=10)
            restart(True)
            metadata = [json.loads(line) for line in query(CUSTOMER_MIGRATIONS_SQL).splitlines() if line.strip()]
            assert metadata == [{'customer_changesets': 3, 'expected_changesets': 3, 'successful_changesets': 3},
                                {'locks': 1, 'unlocked': 1}], metadata
            initial = snapshot()
            restart(True)
            reset = snapshot()
            diff = snapshot_difference(initial, reset)
            assert [r['name'] for r in diff['changed_objects']] == ['cloudbank_customer.customers', 'public.databasechangelog'], diff
            query("UPDATE cloudbank_customer.customers SET customer_name='Retained edit' WHERE customer_id='cust-001';"
                  "INSERT INTO cloudbank_customer.customers(customer_id,customer_name) VALUES ('retained-005','Retained addition');")
            expected = snapshot()
            restart(False)
            assert snapshot() == expected, 'Disabled initialization changed persistent state'
            restart(False)
            assert snapshot() == expected, 'Repeated restart changed persistent state'
            print('MS67_CUSTOMER_STARTUP_INTEGRATION=PASSED; reproduced two-table drift; corrected restarts preserve all state')
    finally:
        subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=60)


if __name__ == '__main__': main()
