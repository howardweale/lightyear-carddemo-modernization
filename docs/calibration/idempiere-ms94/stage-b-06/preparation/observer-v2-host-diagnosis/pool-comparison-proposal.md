# Proposed pool comparison: exact prefix plus a closed HotSpot extension

**Awaiting Howard's approval; diagnostic code only, not production admission.**
Operator review; not independent attestation. No retrospective r10 acceptance.

Policy identifier proposed: `hierarchical-overpass-pool-v1`. It is permitted only
for the already bound HierarchicalTestEngine class SHA-256
`b6ebf7618c7572195ec833104be65f54aaa090263dc14297bd471f9c4a1cd056`,
with its byte-bound TestEngine interface, resolved artifact/loader provenance,
admitted pinned JDK and existing no-transformation/no-shadowing checks. Other
classes continue to require their existing checks; a new mismatch is not learned.

1. Parse and preserve the exact original class file and JDI pool, including tags,
   indices, widths and original method metadata. Reject malformed/truncated data.
2. Require original count 145 and JDI count 159. Require the runtime pool's entire
   original byte range to be **byte-identical**, at the same indices. No prefix
   canonicalization, index renumbering, changed constants or dropped entries.
3. For exactly the fourteen appended entries, recursively resolve index references
   into typed semantic nodes. UTF-8 contents remain exact bytes, represented as hex.
   Only UTF8, Class, String, NameAndType and Methodref tags are admissible. Reject
   cycles, dangling references and every other tag. Preserve multiplicity.
4. Require the resulting sorted multiset to equal precisely:
   - UTF8 `java/lang/AbstractMethodError` and its Class node;
   - UTF8 `<init>` and `(Ljava/lang/String;)V`, their NameAndType and the
     AbstractMethodError constructor Methodref;
   - for **each** of the following inherited abstract methods, its UTF8 name and
     descriptor, plus the exact UTF8 message `Method <owner>.<name><descriptor>
     is abstract` and the corresponding String node:
     - `getId()Ljava/lang/String;`
     - `discover(Lorg/junit/platform/engine/EngineDiscoveryRequest;Lorg/junit/platform/engine/UniqueId;)Lorg/junit/platform/engine/TestDescriptor;`
   Here `<owner>` is the exact slash-form name
   `org/junit/platform/engine/support/hierarchical/HierarchicalTestEngine`.
   The interface's exact bytes must establish those declarations as abstract;
   names or observed error messages alone are not authority.
5. Require every original declared method descriptor, access flags and concrete
   bytecode to remain exact; abstract/native methods retain explicit treatment.
   No additional observed callable method gains trust through this rule. JDI did
   not expose an extra overpass method through methods() in this experiment.
6. Keep both raw hashes and raw material in signed evidence. Recompute the semantic
   extension during independent replay. Its canonical digest is a derived check,
   never a replacement for the bound source bytes or an observed-hash allowlist.

The two experimentally observed extension orders produce the same diagnostic
canonical digest:
`8867c7f7d7c8014a761b09b3862fce79e25be2cc17c224e6bdf63e0b4340ba80`.
This digest includes the source class hash, original pool hash/count and the
typed extension multiset. It is not a global expected digest for other classes.

Five host tests passed: both real extension orders compare equally; changing an
original pool byte fails; changing the AME target or adding a tail entry fails;
wrong counts/source bytes fail; changing a method hash fails. A production
implementation, if approved, must additionally test changed access flags,
interface declarations, code origins and image/loader bindings. The present
diagnostic evaluator intentionally does not pretend to implement those native
admission requirements.

This rule addresses the demonstrated pool mismatch only. It does not approve a
generated lambda, change J1 predicates/outcomes or resolve the complete v2
provenance census. No Docker work precedes explicit approval and a new exact
Tower decision for the expanded five-path census.
