"""Non-submitting authenticated health check; run through agent.py."""
import os
import time
from lightyear_toolkit.client import JudgeClient

client = JudgeClient("http://127.0.0.1:8770", os.environ["LIGHTYEAR_VERIFY_TOKEN"])
for _ in range(60):
    try:
        if client.call("get_budget").get("ok"):
            print('Readiness check passed (get_budget; no submission).')
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit("Readiness failed; inspect sudo journalctl -u lightyear-verify-smoke. Do not reset the session.")
