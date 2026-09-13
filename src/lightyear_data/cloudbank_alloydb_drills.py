"""Controlled AlloyDB workload evacuation with paced application cold starts."""
from .cloudbank_alloydb_recovery import APPLICATION_SNAPSHOT_SQL
from .cloudbank_journeys import SERVICES, require, hashed
from .cloudbank_ms67_drills import FinalDrills


class AlloyDrills(FinalDrills):
    snapshot_sql = APPLICATION_SNAPSHOT_SQL

    def drain_node(self, node):
        current = self.r.get("node", node["name"])
        require(current["metadata"]["uid"] == node["uid"] and current["spec"].get("unschedulable") is True,
                "paced-drain-owned-cordoned-node-required")
        procedure = {"mode": "service-paced-controlled-evacuation", "node_uid_sha256": hashed(node["uid"]),
                     "steps": [], "final_drain_completed": False,
                     "scope": "planned eviction with recovery between services; not simultaneous node loss"}
        self.s.setdefault("evacuation_procedures", []).append(procedure)
        for service in SERVICES:
            self.assert_lease()
            selector = "app.kubernetes.io/name=" + service
            self.intent("paced-drain-" + service, {"node": node["name"], "selector": selector})
            # Includes matching Cloud SQL replicas on this shared node. PDBs
            # still apply, and the enclosing availability sampler stays active.
            self.r.kubectl("drain", node["name"], "--ignore-daemonsets", "--delete-emptydir-data",
                           "--pod-selector=" + selector, "--timeout=600s", timeout=630)
            self.r.wait_ready(service)
            procedure["steps"].append({"service": service, "selector": selector,
                                       "alloydb_replicas_recovered": True, "pdb_enforced": True})
            self.s["pending"] = None
            self.save("paced-drain-recovered-" + service)
        # Evacuate any remaining non-service workloads using the original drain.
        super().drain_node(node)
        procedure["final_drain_completed"] = True
        self.save("paced-node-drain-completed")
