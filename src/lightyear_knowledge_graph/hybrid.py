"""Deterministic projection-only BM25/RRF search. No model downloads or API calls.

The local vector baseline is feature hashing, not a trained language model. Its
small public vocabulary expansion is explicit and versioned, not learned memory.
"""

import hashlib
import math
import re
from collections import Counter, deque
from typing import Protocol
from lightyear_control_tower.decisions import digest

RELATIONS = {"CALLS", "CONTAINS", "USES_COPYBOOK", "HAS_FIELD", "READS", "WRITES"}


def terms(text):
    return re.findall(r"[a-z][a-z0-9]*", text.lower())


class EmbeddingProvider(Protocol):
    provider_id: str
    version: str
    local: bool

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedding:
    provider_id, version, local = "local-feature-hash", "1", True
    vocabulary = {
        "monthly": ("month",),
        "account": ("acct",),
        "balance": ("bal",),
        "calculation": ("compute", "calculate"),
        "interest": ("interest",),
    }

    def embed(self, texts):
        result = []
        for text in texts:
            tokens = terms(text)
            expanded = [
                t for token in tokens for t in (token, *self.vocabulary.get(token, ()))
            ]
            vector = [0.0] * 256
            for token, count in Counter(expanded).items():
                h = hashlib.sha256(token.encode()).digest()
                vector[int.from_bytes(h[:2], "big") % 256] += (
                    1 if h[2] & 1 else -1
                ) * math.log1p(count)
            norm = math.sqrt(sum(v * v for v in vector)) or 1
            result.append([round(v / norm, 10) for v in vector])
        return result


def build_index(projection, provider=None, *, approval=None, trust=None, now=None):
    provider = provider or LocalEmbedding()
    authorization = None
    if not provider.local:
        if projection["mode"] == "confidential":
            raise ValueError("external confidential embeddings forbidden")
        from lightyear_factory.knowledge_trust import approve

        identity = dict(id=provider.provider_id, version=provider.version)
        approve(
            approval,
            trust,
            "embedding-provider-approval",
            dict(
                provider=digest(identity),
                customer=digest(projection["customer_id"]),
                mode=digest(projection["mode"]),
            ),
            ["approved"],
            now=now,
        )
        authorization = approval["decision_sha256"]
    docs = []
    for n in sorted(projection["nodes"], key=lambda n: n["id"]):
        text = " ".join(
            [
                n["name"],
                n.get("statement", ""),
                n.get("properties", {}).get("statement", ""),
                *(s.get("text", "") for s in n.get("source", [])),
                *(
                    a["text"]
                    for a in projection.get("annotations", [])
                    if n["id"] in a["anchors"]
                    and a["provenance"] in {"asserted", "verified"}
                ),
            ]
        )
        docs.append(dict(id=n["id"], text=text, terms=terms(text)))
    vectors = provider.embed([d["text"] for d in docs])
    if len(vectors) != len(docs) or any(
        not v or any(not math.isfinite(x) for x in v) for v in vectors
    ):
        raise ValueError("invalid embeddings")
    if len({len(v) for v in vectors}) > 1:
        raise ValueError("embedding dimension mismatch")
    body = dict(
        schema="projection-search-index/1",
        provider=dict(
            id=provider.provider_id,
            version=provider.version,
            local=provider.local,
            approval=authorization,
        ),
        documents=docs,
        vectors=vectors,
    )
    return {**body, "content_sha256": digest(body)}


def search(projection, query, anchor=None, provider=None):
    index = projection["search_index"]
    if (
        digest({k: v for k, v in index.items() if k != "content_sha256"})
        != index["content_sha256"]
    ):
        raise ValueError("search index hash mismatch")
    provider = provider or LocalEmbedding()
    if (provider.provider_id, provider.version, provider.local) != tuple(
        index["provider"][k] for k in ("id", "version", "local")
    ):
        raise ValueError("search provider mismatch")
    nodes = {n["id"]: n for n in projection["nodes"]}
    if anchor is not None and anchor not in nodes:
        raise ValueError("anchor outside projection")
    docs = index["documents"]
    if set(nodes) != {d["id"] for d in docs}:
        raise ValueError("index outside projection")
    q = set(terms(query))
    n = len(docs)
    avg = sum(len(d["terms"]) for d in docs) / max(1, n) or 1
    df = Counter(t for d in docs for t in set(d["terms"]))
    lexical = {}
    for d in docs:
        counts = Counter(d["terms"])
        lexical[d["id"]] = sum(
            math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            * counts[t]
            * 2.2
            / (counts[t] + 1.2 * (0.25 + 0.75 * len(d["terms"]) / avg))
            for t in q
            if counts[t]
        )
    vector = provider.embed([query])[0]
    similarity = {
        d["id"]: sum(a * b for a, b in zip(vector, v, strict=True))
        for d, v in zip(docs, index["vectors"], strict=True)
    }
    ranks = [
        {
            node: i + 1
            for i, node in enumerate(sorted(scores, key=lambda k: (-scores[k], k)))
            if scores[node] > 0
        }
        for scores in (lexical, similarity)
    ]
    paths = {}
    if anchor:
        adjacent = {}
        for e in projection["edges"]:
            if e["relation"] in RELATIONS:
                adjacent.setdefault(e["source"], set()).add(e["target"])
                adjacent.setdefault(e["target"], set()).add(e["source"])
        paths[anchor] = [anchor]
        todo = deque([anchor])
        while todo:
            a = todo.popleft()
            for b in sorted(adjacent.get(a, ())):
                if b not in paths:
                    paths[b] = [*paths[a], b]
                    todo.append(b)
    scores = {
        node: sum(1 / (60 + r[node]) for r in ranks if node in r) for node in nodes
    }
    if anchor:
        scores = {
            node: s * (1 + 0.25 / len(paths[node]) if node in paths else 1)
            for node, s in scores.items()
        }
    return [
        dict(
            id=node,
            kind=nodes[node]["kind"],
            name=nodes[node]["name"],
            line_ranges=[
                {k: s[k] for k in ("path", "line_start", "line_end")}
                for s in nodes[node].get("source", [])
            ],
            why=dict(
                terms=sorted(
                    q & set(next(d["terms"] for d in docs if d["id"] == node))
                ),
                vector_similarity=(
                    "high"
                    if similarity[node] >= 0.6
                    else "medium" if similarity[node] >= 0.25 else "low"
                ),
                graph_path=paths.get(node, []),
            ),
        )
        for node in sorted(nodes, key=lambda k: (-scores[k], k))
        if scores[node] > 0
    ]
