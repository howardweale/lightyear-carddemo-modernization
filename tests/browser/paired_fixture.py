"""Test-only server with explicitly simulated database observations."""
import json
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from tests.test_paired_campaign import PairedCampaignTests, SimulatedRunner
from lightyear_workflow.campaign_engine import execute
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph

fixture = PairedCampaignTests()
fixture.setUp()
shutil.copytree(ROOT / 'knowledge/viewer', fixture.root / 'knowledge/viewer')
class SlowSimulation(SimulatedRunner):
    def observe(self, lane, case):
        time.sleep(.12)
        return super().observe(lane, case)
def launch(root, run_id):
    threading.Thread(target=lambda: execute(root, run_id, runner_factory=SlowSimulation), daemon=True).start()
fixture.service.dispatcher = launch
graph = ROOT / 'knowledge/composite/estate.snapshot.json.gz'
server = ExplorerServer(('127.0.0.1', 0), GraphExplorerIndex(load_graph(graph)), fixture.root / 'knowledge/viewer', graph_path=graph)
server.campaign_service = fixture.service
credential = fixture.root / 'work/campaigns/oracle26ai-alloydb-number/operator/authority.credential.txt'
print(json.dumps({'port': server.server_port, 'credential': credential.read_text().strip()}), flush=True)
try: server.serve_forever()
finally: server.server_close(); fixture.doCleanups()
