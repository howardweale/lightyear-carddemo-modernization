# Prospective bound-hierarchy pool comparison v2 — approval required

This proposal has not been enabled. The approved HierarchicalTestEngine hash,
145→159 counts, exact original prefix and declared-method checks remain unchanged.
No existing evidence is reclassified.

For an abstract class only:

1. Read its original class file and the complete superclass/interface closure
   from independently bound artifacts. Record every hash. Reject missing bytes,
   name mismatches, cycles and default-interface methods in this first version.
2. Derive required abstract method name/descriptors from that closure. The
   most-derived class declaration determines whether a concrete implementation
   satisfies a requirement. Private/static methods and constructors contribute
   nothing. An empty required set is not an overpass exception.
3. Require the entire original constant pool to remain a byte-identical prefix.
   Require exactly six shared extension entries plus four entries for each
   derived method. No other extension tags or nodes are allowed.
4. Resolve the extension into a semantic multiset containing only the UTF-8,
   Class, String, NameAndType and Methodref nodes for
   `java/lang/AbstractMethodError.<init>(Ljava/lang/String;)V` and each exact
   `Method <internal-class>.<method><descriptor> is abstract` message/name/type.
   Reject unknown, missing, cyclic, duplicated or extra nodes against exact counts.
5. Re-check every declared method's byte hash and access flags. Original code
   still references the original pool indices; added pool data cannot replace
   code or flags. Record the raw runtime pool hash and bound hierarchy hashes.

The diagnostic prototype is `tools/b06_host_probe/pool_proposal_v2.py`.
Its result explicitly says `production_admission: false` and
`approval_required: true`. Synthetic positive/negative tests establish parser
behavior, not that the pinned native HotSpot uses this rule for every class.
Before production admission, review actual native instances and add them to the
five-path census proof. This proposal changes no journey verdict or predicate.
