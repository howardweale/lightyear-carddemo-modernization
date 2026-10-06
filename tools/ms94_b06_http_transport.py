"""B06 r8 argument construction. No process launch or model-call authority."""
from tools.ms94_b06_http_transport_draft import draft

CREDENTIAL_STORE = 'cli_auth_credentials_store="file"'


def arguments(port, empty_workspace):
    value = draft(port, empty_workspace)
    value['artifact_type'] = 'ms94-b06-http-exec-preparation/2'
    value['argv'][1:1] = ['--config', CREDENTIAL_STORE]
    value['credential_store'] = 'file'
    value['authentication_home_policy'] = 'dedicated-builder-only; no copied operator credentials'
    return value


def login_arguments(*, status=False):
    return ['--config', CREDENTIAL_STORE, 'login', *(['status'] if status else ['--device-auth'])]
