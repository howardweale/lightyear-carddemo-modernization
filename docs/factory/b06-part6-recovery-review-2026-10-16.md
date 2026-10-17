# B06 Part 6 recovery review — October 16, 2026

The Windows files are accessible. Six public-key signatures (terminal, cleanup and inventory for both attempts), request/plan bindings, and the four report-file hashes were reverified read-only. Evidence index: b06-part6-reverification-2026-10-16.json.

This is a recovery review of the October 13 report. No raw capture was reread, no current resource-absence probe was run, and no new experiment occurred. Full inventory-byte verification and owned-resource absence described below were performed on October 13; today's verification covers signed metadata and report hashes. Both attempts remain consumed; no cause was identified and no new authority is granted.

The following excerpt is from the hash-verified October 13 Part 6 report; dates and verification claims in it refer to October 13.

# B06 R4 Part 6 — final operator review

**Cause not identified under the preregistered criteria. Both attempts are consumed. No third attempt or further observer repair.**

Attempt 2 ran once in diagnostic mode and stopped when an eleventh unmatched return would exceed the cap of ten. Its signed terminal outcome is `refused`. Cleanup was sealed at **2:51:42 PM PDT, October 13**, before the 5 PM deadline. Public verification of terminal, cleanup, handoff and all **2,833 inventory members** passed. Fresh read-only checks confirmed absence of owned containers, networks and volumes; the lease is gone. The supervisor exit code 0 reports completed refusal/cleanup, not experimental success.

Request seal: `7e5270c1457aafbe5872df08b4d5ae1f80caba9c6b48ccae379adc6cd9062901`
Source commit: `ac9f533822576170ac2f1b6bf25f66ce22a25033`
Attempt-2 owner: `journey-b39c679edb1b49ef94b98797969b6ea4`

## Every unmatched return in attempt 2

Trigger is the JDI event sequence. Record is the subsequent diagnostic event, or the guard stop for #11. Generation counts are recorded entries, not completed matching returns. Every row has the signed active phase **application-worker-started**.

| Return | Trigger sequence | Diagnostic/guard sequence | Generation entries | Nearest preceding lifecycle |
| --- | ---: | ---: | ---: | --- |
| 1 | 22,855 | 22,856 | 1,614 | 22849: deleted request 1695 (method-exit, thread 16392) |
| 2 | 22,992 | 22,993 | 1,624 | 22990: enabled request 1706 (method-exit, thread 16392) |
| 3 | 26,089 | 26,090 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 4 | 26,098 | 26,099 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 5 | 26,115 | 26,116 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 6 | 26,130 | 26,131 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 7 | 26,171 | 26,172 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 8 | 26,194 | 26,195 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 9 | 26,205 | 26,206 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 10 | 26,226 | 26,227 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |
| 11 — cap stop | 26,239 | 26,240 | 1,836 | 26076: deleted request 1899 (method-exit, thread 8311) |

All triggering returns are `MethodHandles$Lookup$ClassDefiner.defineClass`, return breakpoint request **25**, code index **155**. Their threads differ from the unrelated preceding method-exit requests. Ten continuation records are present; the eleventh is represented by the JDI trigger and `observer-resource-limit` guard record, not an eleventh continuation.

## Lifecycle and class-prepare context

For #1, the nearest following lifecycle event is **22,862**, created method-exit request **1696** for `ClassLoader.defineClass`, thread **8311**. For #2 it is **22,996**, created method-exit request **1707**, same ClassLoader method/thread. No later lifecycle event exists after **26,076**, so #3–#11 have no following lifecycle event. All observed class-prepare records occur at sequences **31, 46, 81 and 14,412**; none occurs around these unmatched returns.

The complete per-return ±100-sequence context and nearest records on both sides are included below and in the JSON. This interval is only an excerpting convention; it does not change either registered criterion.

## Exact preregistered criteria

**Criterion (a): NOT SUPPORTED.** The first unmatched return is 26,184 in attempt 1 and 22,855 in attempt 2. In both streams, entry request 24 is enabled at sequence 83 and return request 25 at sequence 85, with null thread filters. No relevant disabled request, class redefinition/reload or thread-filter mismatch explains the missed entry. Nearby method-exit transitions on other request IDs/threads do not establish that explanation.

**Criterion (b): NOT SUPPORTED.** `application-worker-started` is the active phase at every unmatched return. It does not identify a particular application operation. Neither attempt reproduces a specific operation near 12,400 generations.

**Recorded finding:** attempt 1 stopped after **1,810** entries, approximately **10,590 fewer** than the earlier ~12,400 point. Attempt 2 first encountered an unmatched return at **1,614**, then reached **1,836** at its cap-stop. The projected ~18,826 first-stop point was not observed. This shift is a finding, not a new causal criterion. Historical raw evidence was not altered or reread.

## Counts, resources and witnesses

| Metric | Attempt 2 | Approved cap |
| --- | ---: | ---: |
| Ordinary records | 5,767 | 150,000 |
| Ordinary wire bytes | 63,592,008 | Shared 8 GiB output cap |
| Metadata records | 20,473 | 1,500,000 |
| Metadata wire bytes | 4,395,077 | 402,653,184 (384 MiB) |
| Final retained file bytes | 376,317,737 | 8,589,934,592 (8 GiB) |
| Reported heap high-water | 18,120,080 | 1,536 MiB configured heap; 85% guard |

Wire byte counts use the pinned Java serializer on authenticated stored events; signed-envelope/newline bytes are excluded. Output is final retained size, not a transient disk peak. Heap is a sampled high-water, not a terminal peak. The guard reason was **unmatched-return-cap-10**, not heap or disk. A complete **60,010-byte** class histogram was sealed; no heap dump was produced.

| Input-witness classification | Entries |
| --- | ---: |
| bootstrap-only-captured-input-candidate | 430 |
| unresolved-bytecode-input-only | 1,139 |
| application-derived-input | 267 |

All 1,836 generation input witnesses passed the existing validator. Bootstrap-only candidates do not establish image independence. Bytecode-only inputs remain unresolved; caller stacks are not treated as generation inputs.

## Timing and verified hashes

Attempt 1: **898.938 seconds**. Attempt 2: **1,022.140 seconds (17m 2.140s)**, including **660.500 seconds** observer preparation and approximately **40.410 seconds** application execution until stop request. Both attempts together consumed **1,921.078 seconds**. The signed attempt-2 terminal is dated **2026-10-13T21:51:42.453595Z** (2:51:42 PM PDT), leaving over two hours before the cleanup deadline. No remaining time authorizes a third attempt.

| Attempt-2 artifact | Content seal | File SHA-256 |
| --- | --- | --- |
| terminal.json | `40ec80717ebb978d18345058b22f0fc3bd7adc3aa96af57614702b4ad3273c3e` | `70f145c4f9ea479a83c9905f2f7a6746681570a4977b46cc9529370278eb6445` |
| artifacts.json | `5a9d2b02ec0d38809a14968e0c3c3c60d32eea6e83928974e7ad1cabe24a81f0` | `001bf46244be576bc606e661b1cfcac13cec09b9fe87248f7c1085f18aafa679` |
| cleanup.json | `d0501c558abb0ae6c37322956a7e0e8fe17cffc1286a6e7b0d8754f48ac64b14` | `f7d32a5a51c1cefc2306a97354c2a7753fc07b72bf2c864545630835883cb26c` |
| engineering.json | `9b57043b3ebd95d56646ce1a71fb51c6eb8d95dc4892aa15f3970bff8cd7caff` | `cee5c7cf95ee6e016a20ffe02c98442adc1e7d71c53a94c6f488b78bedd6be1c` |
| plan.json | `6b2634d54b48377b047726506bf8a800e6f73dbbf0409d76ccf1c87e865df78d` | `b832e1d6d7b915d25e69cf48ebdd79b2cc983695d70581894944759bf8fe510d` |
| posting-observer/oracle/guard-stop.json | `f8b1ab5d0d8fdca3c645fd1a09f4223e78a9b3dd8ee5027bd0c42063ce23a0e7` | `4b3e48acbcd43ec68dafbd943a80191149772576ae42c1e3247c858b8b283a50` |

Guard histogram SHA-256: `51e81ed7b256e7dc48129f64aac049b36a8c10a1f05e5ac07b9211ac66cd33e4`

No separate archive was created; the signed artifacts.json inventory binds every retained run file. Source, request, settings and observer bytes were unchanged. This report is AI-assisted operator review, not independent attestation or qualification/measurement credit.


## Explicit known test limitations (27)

All 27 were skipped in the inspected October 11 exact-62eafdaf CI logs. The 78 focused regressions have no recovered per-test roster; equivalent local coverage cannot be certified. None is newly credited by either live attempt.

- test_original_junit_and_fixture_definition_returns (test_b06_dynamic_target_proof.LocalDefinitionTests.test_original_junit_and_fixture_definition_returns)
- test_all_framework_lambdas_and_public_role_lambdas (test_b06_generated_linkage.LocalJdiGeneratedTests.test_all_framework_lambdas_and_public_role_lambdas)
- test_changed_or_missing_method_access_flags_fail (test_b06_host_pool_proposal.PoolProposalTests.test_changed_or_missing_method_access_flags_fail)
- test_method_changes_are_not_hidden_by_pool_comparison (test_b06_host_pool_proposal.PoolProposalTests.test_method_changes_are_not_hidden_by_pool_comparison)
- test_missing_count_or_changed_source_fail (test_b06_host_pool_proposal.PoolProposalTests.test_missing_count_or_changed_source_fail)
- test_prefix_corruption_is_never_normalized (test_b06_host_pool_proposal.PoolProposalTests.test_prefix_corruption_is_never_normalized)
- test_two_real_runtime_orders_canonicalize_equally (test_b06_host_pool_proposal.PoolProposalTests.test_two_real_runtime_orders_canonicalize_equally)
- test_wrong_error_target_and_unknown_tail_fail (test_b06_host_pool_proposal.PoolProposalTests.test_wrong_error_target_and_unknown_tail_fail)
- test_class_data_initializers_and_changed_object_fail_closed (test_b06_lambda_form_experiment.LocalLambdaFormTests.test_class_data_initializers_and_changed_object_fail_closed)
- test_emitter_return_and_actual_definition_bytes_match (test_b06_lambda_form_experiment.LocalLambdaFormTests.test_emitter_return_and_actual_definition_bytes_match)
- test_expression_match_does_not_claim_full_proof (test_b06_lambda_form_experiment.LocalLambdaFormTests.test_expression_match_does_not_claim_full_proof)
- test_extra_logic_and_wrong_graph_fail (test_b06_lambda_form_experiment.LocalLambdaFormTests.test_extra_logic_and_wrong_graph_fail)
- test_forged_emitter_array_loader_or_graph_fails (test_b06_lambda_form_experiment.LocalLambdaFormTests.test_forged_emitter_array_loader_or_graph_fails)
- test_immediate_test_body_waits_for_complete_or_specific_error (test_b06_transient_agent.EquinoxAgentTests.test_immediate_test_body_waits_for_complete_or_specific_error)
- test_jvm_exit_writes_specific_error (test_b06_transient_agent.EquinoxAgentTests.test_jvm_exit_writes_specific_error)
- test_large_transient_set (test_b06_transient_agent.EquinoxAgentTests.test_large_transient_set)
- test_real_folder_bundle_then_mutation_during_worker_capture (test_b06_transient_agent.EquinoxAgentTests.test_real_folder_bundle_then_mutation_during_worker_capture)
- test_actual_external_capture_and_both_method_handle_paths (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_actual_external_capture_and_both_method_handle_paths)
- test_captured_storage_field_does_not_admit_its_methods (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_captured_storage_field_does_not_admit_its_methods)
- test_definition_refresh_cannot_reuse_an_earlier_generated_proof (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_definition_refresh_cannot_reuse_an_earlier_generated_proof)
- test_extra_lambda_logic_even_with_recomputed_hash_fails (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_extra_lambda_logic_even_with_recomputed_hash_fails)
- test_missing_use_graph_and_opaque_target_fail (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_missing_use_graph_and_opaque_target_fail)
- test_missing_younger_target_is_not_replaced_by_deeper_candidate (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_missing_younger_target_is_not_replaced_by_deeper_candidate)
- test_reviewed_pool_rule_is_used_by_native_ordinary_binding (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_reviewed_pool_rule_is_used_by_native_ordinary_binding)
- test_wrong_class_source_and_loader_do_not_bind (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_wrong_class_source_and_loader_do_not_bind)
- test_wrong_host_loader_or_returned_class_fails (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_wrong_host_loader_or_returned_class_fails)
- test_wrong_or_mutated_field_layout_fails (test_ms94_b06_observer_v2.ActualCollectorAdversarialTests.test_wrong_or_mutated_field_layout_fails)

## Separate exact-62eafdaf CI passes (20)

These are prior CI evidence only, not executions in the October 13 window.

- test_actual_bounded_jdi_emission_and_ten_unmatched_cap (test_b06_bounded_format.BoundedHostTests.test_actual_bounded_jdi_emission_and_ten_unmatched_cap)
- test_actual_defined_bytes_and_duplicate_definition_error (test_b06_build_once_agent.BuildOnceAgentTests.test_actual_defined_bytes_and_duplicate_definition_error)
- test_exact_production_java_guard_reproduces_captured_refusal (test_b06_captured_refusal.CapturedRefusalTests.test_exact_production_java_guard_reproduces_captured_refusal)
- test_real_java_encoder_matches_python_dictionary_and_decoder (test_b06_compact_wire.CompactWireTests.test_real_java_encoder_matches_python_dictionary_and_decoder)
- test_module_access_missing_refuses_before_collection (test_b06_jdi_mirrors.MirrorCacheTests.test_module_access_missing_refuses_before_collection)
- test_real_host_lifecycle_identity_queries_and_fail_closed_bounds (test_b06_jdi_mirrors.MirrorCacheTests.test_real_host_lifecycle_identity_queries_and_fail_closed_bounds)
- test_real_jdi_and_failure_context_before_refusal (test_b06_observer_audit.AuditHostTests.test_real_jdi_and_failure_context_before_refusal)
- test_exact_slices_bounded_packets_and_invalid_reads (test_b06_observer_bulk_reads.BulkReadTests.test_exact_slices_bounded_packets_and_invalid_reads)
- test_real_jdi_large_offset_definitions_and_hidden_bytes (test_b06_observer_bulk_reads.BulkReadTests.test_real_jdi_large_offset_definitions_and_hidden_bytes)
- test_real_agent_records_installed_bundle_without_waiting_for_resolution (test_b06_observer_host_r3.HostObserverTests.test_real_agent_records_installed_bundle_without_waiting_for_resolution)
- test_real_generation_events_direct_hidden_and_failed_definition_unwind (test_b06_observer_host_r3.HostObserverTests.test_real_generation_events_direct_hidden_and_failed_definition_unwind)
- test_v2_recursive_catch_real_jdi (test_b06_observer_host_r3.HostObserverTests.test_v2_recursive_catch_real_jdi)
- test_queued_start_resume_with_delayed_dispatch_and_concurrent_generation (test_b06_observer_startup.ObserverStartupTests.test_queued_start_resume_with_delayed_dispatch_and_concurrent_generation)
- test_return_arm_rejects_missing_or_changed_activation (test_b06_observer_startup.ObserverStartupTests.test_return_arm_rejects_missing_or_changed_activation)
- test_actual_java_rejects_strict_or_mixed_expanded_quota (test_b06_oct13.JavaQuotaTests.test_actual_java_rejects_strict_or_mixed_expanded_quota)
- test_input_descriptor_does_not_materialize_definitions_or_extra_class_objects (test_b06_oct13.JavaQuotaTests.test_input_descriptor_does_not_materialize_definitions_or_extra_class_objects)
- test_fixed_retained_storage_preserves_activation_identity (test_b06_pending_pool.PendingPoolTests.test_fixed_retained_storage_preserves_activation_identity)
- test_production_serializer_at_85_percent_192_mib_heap (test_b06_transient_peak.TransientPeakTests.test_production_serializer_at_85_percent_192_mib_heap)
- test_captured_operands_continue_without_creating_activation (test_b06_unmatched_return.DiagnosticHostTests.test_captured_operands_continue_without_creating_activation)
- test_real_host_jdi_collection_continues_after_missing_outer_entry (test_b06_unmatched_return.DiagnosticHostTests.test_real_host_jdi_collection_continues_after_missing_outer_entry)