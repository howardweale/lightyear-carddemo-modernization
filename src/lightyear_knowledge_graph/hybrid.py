"""Deterministic projection-only BM25/RRF search. No model downloads or API calls.

The default is keyword plus graph-proximity search. Semantic ranking requires a
separately pinned local provider and a passing held-out benchmark.
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
    provider_id, version, local = "keyword-only", "2", True

    def embed(self, texts):
        return [[0.0] for _ in texts]


def indexable(node):
    return 'literal' not in node['kind'].lower() and not re.fullmatch(r'[\W\d_]+',node['name'])


def abbreviations(nodes):
    """Learn only explicit expansion notation in approved source comments."""
    candidates={}
    for node in nodes:
        for source in node.get('source',[]):
            for line in source.get('text','').splitlines():
                if not ('*>' in line or len(line)>6 and line[6]=='*'):continue
                for word,short in re.findall(r'\b([A-Za-z]{4,})\s*\(([A-Z]{2,6})\)',line):
                    if len(short)<len(word):candidates.setdefault(short.lower(),set()).add(word.lower())
    return {short:next(iter(words)) for short,words in sorted(candidates.items()) if len(words)==1}


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
    vocabulary=abbreviations(projection['nodes'])
    for n in sorted(projection["nodes"], key=lambda n: n["id"]):
        if not indexable(n):continue
        text = " ".join(
            [
                n["name"],
                n.get("statement", ""),
                n.get("properties", {}).get("statement", ""),
                *(s.get("text", "") for s in n.get("source", [])),
            ]
        )
        tokens=terms(text)
        docs.append(dict(id=n["id"], text=text, terms=[*tokens,*(vocabulary[t] for t in tokens if t in vocabulary)]))
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
        abbreviations=vocabulary,
    )
    return {**body, "content_sha256": digest(body)}


def search(projection, query, anchor=None, provider=None, *, top_k=100, kind=''):
    if type(top_k) is not int or not 1<=top_k<=1000:raise ValueError('search top_k')
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
    if {n['id'] for n in nodes.values() if indexable(n)} != {d["id"] for d in docs}:
        raise ValueError("index outside projection")
    q = set(terms(query))
    q |= {index.get('abbreviations',{})[t] for t in list(q) if t in index.get('abbreviations',{})}
    term_sets={d['id']:set(d['terms']) for d in docs}
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
        d['id']: sum(1 / (60 + r[d['id']]) for r in ranks if d['id'] in r) for d in docs
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
                    q & term_sets[node]
                ),
                vector_similarity=(
                    "high"
                    if similarity[node] >= 0.6
                    else "medium" if similarity[node] >= 0.25 else "low"
                ),
                graph_path=paths.get(node, []),
            ),
        )
        for node in sorted((n for n in scores if scores[n]>0 and (not kind or nodes[n]['kind']==kind)),
                           key=lambda k: (-scores[k], k))[:top_k]
    ]
