"""Bounded read-only graph context over an approved in-memory projection."""
import base64
import hashlib
import hmac
import json
import secrets
import re
from datetime import date, datetime, timezone
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest
from lightyear_knowledge_graph.explorer import GraphExplorerIndex
from .workspace import Refused
from .graph_approval import load_approved


class GraphTools:
    def active(self):
        return date.fromisoformat(self.decision["review_after"]) > datetime.now(timezone.utc).date()

    def __init__(self, payload, manifest, decision, workspace, client, *, cap=8192, revocations=None, embedding_provider=None):
        if type(cap) is not int or not 1024 <= cap <= 32768:
            raise Refused("graph-response-cap")
        self.payload, self.manifest, self.decision = payload, manifest, decision
        self.workspace, self.client, self.cap = Path(workspace), client, cap
        self.hash = manifest["projection_sha256"]
        self.key = secrets.token_bytes(32)
        self.revocations=revocations
        self.embedding_provider=embedding_provider
        # No source graph, evidence pack, ontology or publication file is loaded.
        self.index = GraphExplorerIndex(payload, ontology={"relations": {}}, projection_only=True)

    @classmethod
    def approved(cls, directory, proof, trust, workspace, client):
        data, manifest, decision = load_approved(directory, proof, trust)
        task = client.call("get_task")
        if (task.get("context_projection_sha256") != manifest["projection_sha256"] or
                task.get("disclosure_mode") != manifest["mode"] or
                task.get("context_lane_sha256") != manifest["lane_sha256"]):
            raise Refused("graph-judge-context-mismatch")
        revocations=None
        if data.get('annotations'):
            from .revocations import RevocationReader
            revocations=RevocationReader(Path(directory)/'revocations',data['revocation_binding'],manifest['projection_sha256'])
            revocations.read()
        provider=None
        if data.get('search_index',{}).get('provider',{}).get('id')=='local-onnx-mean-pooling':
            from lightyear_knowledge_graph.local_onnx import LocalOnnxEmbedding
            config=trust['local_embeddings']
            provider=LocalOnnxEmbedding(config['directory'],config['manifest'])
            if provider.version!=data['search_index']['provider']['version']:raise Refused('embedding-binding')
        return cls(data, manifest, decision, workspace, client,revocations=revocations,embedding_provider=provider)

    def _cursor(self, query, offset):
        raw = canonical([self.hash, query, offset])
        return base64.urlsafe_b64encode(raw + hmac.digest(self.key, raw, "sha256")).decode()

    def _offset(self, query, cursor):
        if not cursor:
            return 0
        try:
            if len(cursor) > 4096:
                raise ValueError()
            data = base64.urlsafe_b64decode(cursor)
            raw, mac = data[:-32], data[-32:]
            identity, q, offset = json.loads(raw)
            if (not hmac.compare_digest(mac, hmac.digest(self.key, raw, "sha256")) or
                    identity != self.hash or q != query or type(offset) is not int or offset < 0):
                raise ValueError()
            return offset
        except Exception:
            raise Refused("graph-cursor-invalid") from None

    def _page(self, rows, query, limit, cursor=""):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise Refused("graph-limit")
        offset = self._offset(query, cursor)
        page = dict(projection_sha256=self.hash, truncated=False, items=[], cursor=None)
        consumed = 0
        for row in rows[offset:offset+limit]:
            candidate = {**page, "items": [*page["items"], row],
                         "cursor": self._cursor(query, offset+consumed+1), "truncated": True}
            if len(canonical(candidate)) > self.cap:
                if not page["items"]:
                    # Make progress even for an individually oversized node.
                    small = {k:v for k,v in row.items() if k in {"id","kind","name","relation","direction"}}
                    small = {k:v[:160] if isinstance(v,str) else v for k,v in small.items()}
                    page["items"].append({**small,"item_truncated":True})
                    consumed += 1
                    page["truncated"] = True
                break
            page["items"].append(row); consumed += 1
        more = offset + consumed < len(rows)
        page["truncated"] = page["truncated"] or more
        page["cursor"] = self._cursor(query, offset+consumed) if more else None
        if len(canonical(page)) > self.cap:
            raise Refused("graph-response-cap")
        return page

    def call(self, tool, **args):
        try:
            if not self.active():
                raise Refused("graph-approval-expired")
            result = getattr(self, "_" + tool)(**args)
        except Exception:
            result = dict(projection_sha256=self.hash, truncated=False, error="graph-request-refused")
        # Informational agent-controlled append-only log; never used by the judge.
        path = self.workspace / "graph-queries.jsonl"
        if path.is_symlink() or getattr(path, "is_junction", lambda:False)():
            raise Refused("graph-log-path")
        with path.open("ab") as f:
            f.write(canonical(dict(tool=tool, arguments_sha256=digest(args),
                response_bytes=len(canonical(result)), timestamp=datetime.now(timezone.utc).isoformat()))+b"\n")
        return result

    def _graph_search(self, query, kind="", limit=10, cursor="", mode="lexical", anchor=None):
        if not isinstance(query,str) or len(query)>512 or not 1 <= limit <= 25:
            raise Refused("graph-search-input")
        if mode not in {"lexical", "hybrid"}:
            raise Refused("graph-search-mode")
        if mode == "hybrid":
            from lightyear_knowledge_graph.hybrid import search
            rows = search(self.payload, query, anchor, provider=self.embedding_provider,top_k=1000, kind=kind)
            return self._page(rows, digest(["hybrid", query, kind, anchor]), limit, cursor)
        # Reuse explorer ranking/search; fetch all pages before response-byte paging.
        rows = []
        for offset in range(0, len(self.index.node_by_id), 100):
            found = self.index.search(query, kind, 100, audience="implementer",
                                     customer_id=self.payload["customer_id"], offset=offset)
            rows.extend(dict(id=n["id"], kind=n["kind"], name=n["name"],
                summary=n["statement"].split("\n")[0][:240],
                provenance=self.index.node_by_id[n["id"]]["properties"]["provenance"]) for n in found)
            if len(found)<100: break
        return self._page(rows, digest(["search",query,kind]),limit,cursor)

    def _graph_guidance(self, node_id):
        from .guidance import guidance
        return guidance(self.payload, [node_id], cap=min(4096, self.cap),revocations=self.revocations)

    def _graph_node(self, node_id, include_source=False):
        if type(include_source) is not bool:
            raise Refused("graph-source-flag")
        self.index.node(node_id, audience="implementer")  # audience check
        n = self.index.node_by_id[node_id]
        row = {k:n[k] for k in ("id","kind","name","properties")}
        if include_source:
            row["source"] = n["source"]
        row["verified_by"] = [e["target"] for e in self.payload["verified_by"] if e["source"] == node_id]
        return self._page([row], digest(["node",node_id,include_source]),1)

    def _graph_neighbors(self, node_id, relations=None, direction="both", depth=1, limit=25, cursor=""):
        if direction not in {"in","out","both"} or type(depth) is not int or depth not in {1,2} or not 1<=limit<=25:
            raise Refused("graph-neighbors-input")
        relations = relations or []
        if not isinstance(relations,list) or len(relations)>50 or not all(isinstance(r,str) for r in relations):
            raise Refused("graph-relations")
        selection = self.index.neighborhood(node_id, depth, audience="implementer",
            limit=len(self.index.node_by_id), relations=tuple(relations), direction=direction)
        rows = []
        for e in selection.edges:
            other = e["target"] if e["source"] == node_id else e["source"]
            n = self.index.node_by_id[other]
            rows.append(dict(relation=e["relation"], source=e["source"], target=e["target"],
                direction="out" if e["source"] == node_id else "in" if e["target"] == node_id else "indirect",
                id=n["id"], kind=n["kind"], name=n["name"]))
        return self._page(rows, digest(["neighbors",node_id,relations,direction,depth]),limit,cursor)

    def references(self, node_id):
        node = self.index.node_by_id[node_id]
        if node["kind"] != "cobol_field":
            raise Refused("graph-reference-kind")
        pattern = re.compile(r"(?<![\w-])"+re.escape(node["name"])+r"(?![\w-])", re.I)
        return [dict(id=n["id"],kind=n["kind"],name=n["name"],
            line_ranges=[{k:s[k] for k in ("path","line_start","line_end")} for s in n["source"] if pattern.search(s.get("text",""))],
            provenance="observed (lexical)")
            for n in self.payload["nodes"] if n["kind"] in {"cobol_paragraph","cobol_program"}
            and any(pattern.search(s.get("text","")) for s in n["source"])]

    def _graph_references(self, node_id, cursor=""):
        return self._page(self.references(node_id), digest(["references",node_id]),50,cursor)

    def _explain_divergence(self, attempt_id, cursor=""):
        verdict = self.client.call("get_verdict", attempt_id=attempt_id)
        if not verdict.get("ok") or verdict.get("verdict") == "pending":
            return self._page([],digest(["explain",attempt_id]),50)
        rows = []
        for d in verdict.get("diagnostics", []):
            dataset = d.get("dataset")
            if self.payload["mode"] == "confidential" or d.get("field") in {None,"$record"}:
                layouts = self.payload["dataset_copybooks"].get(dataset, [])
                ids = {n["id"] for n in self.payload["nodes"] if n["kind"]=="copybook" and n["name"] in layouts}
                rows.extend(dict(id=n,kind="copybook",name=self.index.node_by_id[n]["name"]) for n in sorted(ids))
                names = self.payload.get("dataset_file_names", {}).get(dataset, [])
                file_ids = {n["id"] for n in self.payload["nodes"]
                            if n["kind"] in {"cobol_file_handle","dataset"} and n["name"] in names}
                for e in self.payload["edges"]:
                    if e["relation"] in {"WRITES","READS_WRITES"} and e["target"] in file_ids:
                        n=self.index.node_by_id[e["source"]]
                        rows.append(dict(id=n["id"],kind=n["kind"],name=n["name"]))
                for n in self.payload["nodes"]:
                    if n["kind"]=="cobol_paragraph" and any(
                        re.search(r"\b(?:REWRITE|WRITE)\s+"+re.escape(name)+r"\b",s.get("text",""),re.I)
                        for name in names for s in n["source"]):
                        rows.append(dict(id=n["id"],kind=n["kind"],name=n["name"],provenance="observed (lexical)"))
            else:
                name = d["field"].split(".")[-1]
                for n in self.payload["nodes"]:
                    if n["kind"]=="cobol_field" and n["name"]==name:
                        parents = [self.index.node_by_id[e["source"]]["name"] for e in self.payload["edges"]
                                   if e["target"]==n["id"] and e["relation"]=="HAS_FIELD"]
                        rows.append(dict(id=n["id"],kind=n["kind"],name=n["name"],copybooks=parents))
                        rows.extend(self.references(n["id"]))
        rows=list({digest(r):r for r in rows}.values())
        return self._page(rows,digest(["explain",attempt_id]),50,cursor)
