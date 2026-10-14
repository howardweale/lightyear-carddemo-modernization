# B06 R4 exact binding review

**Preparation only. No new go received; no operational signing, native run or merge.**

Execution commit: `ac9f533822576170ac2f1b6bf25f66ce22a25033`.
Request seal: `7e5270c1457aafbe5872df08b4d5ae1f80caba9c6b48ccae379adc6cd9062901`.
Request file SHA-256: `5fe273fcffe2c6c299cc3ff4fff1784ff56a5c0c3af7112fd27d844e4ef8b6c5`.
Delivered at: 2026-10-13T16:18:49Z.

Required future go line (not yet authorized):
```text
go B06 ac9f533822576170ac2f1b6bf25f66ce22a25033 7e5270c1457aafbe5872df08b4d5ae1f80caba9c6b48ccae379adc6cd9062901
```

## Template diff

observer_source is a request field, not a template field; exactly two template payload hash values change, plus its computed content seal. The request observer_source equals the new implementation commit.

| Field | R3 | R4 |
| --- | --- | --- |
| /content_sha256 | `bd0ade82a34af685750eb871a56ff4869529bddceb54e1371d719a85e47218f8` | `d9e10a3f95dac064e2464e847faaf9dfbd43c81cd59efdfb1ec278b82bfb56be` |
| /implementation_sha256/tools/ms94_b06_engineering_key.py | `ec787f53e818685b86d33185665d64bd19d87fac0ba11eb740f41a2b6baebc7b` | `d4b6a05d32d5fd43de0490de4197b21462d8407926cf079e8c49aeb528ce7cb8` |
| /implementation_sha256/tools/ms94_b06_oct13_authorization.py | `3dffd253dd72c5619bf69f4711f75532aed3444fd1f2053288ec58ea91f4742b` | `f860aa52e7482a8f5062c11a6474256db66ff4da529e8f1ec955d2f0a73ee1af` |

Both new file hashes were computed directly from `git show ac9f5338:<path>` and equal the template entries. Existing template() from that clean checkout verified all 111,311 bound files in 59.110 seconds. The original template was separately recovered exactly before applying Howard's narrow exception.

## Request field-by-field diff

| Field | R3 | R4 |
| --- | --- | --- |
| asset_index_file_sha256 | `"226ccc88328b73c551304ec5d08b3be9d669fe4f6fdbc722e83583f56ed83926"` | `"eca5be823558680239eca08f08f39bbe21db5ce8a0ad0ca044f7f00c1f33ef9b"` |
| asset_index_sha256 | `"19df0da05eafb6eaef950d91ae6b45094ec9835e717ddd266b105d5ec70fd518"` | `"b5314039a6af11e89cfdd532ca669eb38f0b6eefeb8e935726b2b13176ca2329"` |
| content_sha256 | `"107c20733d9bc7862461b6e13ba4c180cdf1dad160f51be410c5523587900f35"` | `"7e5270c1457aafbe5872df08b4d5ae1f80caba9c6b48ccae379adc6cd9062901"` |
| deadline_utc | `"2026-10-13T19:00:00Z"` | `"2026-10-14T00:00:00Z"` |
| engineering_key_sha256 | `"4ce00cfa28c13f74c12e6569b6aae010fe7e7185849accad8340c2fc367be9f0"` | `"6d4083d20e5d17e5d3be07dd660621f913cfd50da60c68a361fe628565f7aa7f"` |
| full_plan_delivered_at_utc | `"2026-10-11T22:19:17Z"` | `"2026-10-13T16:18:49Z"` |
| implementation_commit | `"62eafdaf29dce1d40603d38c3a394f150b98f686"` | `"ac9f533822576170ac2f1b6bf25f66ce22a25033"` |
| native_template_sha256 | `"bd0ade82a34af685750eb871a56ff4869529bddceb54e1371d719a85e47218f8"` | `"d9e10a3f95dac064e2464e847faaf9dfbd43c81cd59efdfb1ec278b82bfb56be"` |
| not_before_utc | `"2026-10-13T16:00:00Z"` | `"2026-10-13T21:00:00Z"` |
| observer_source | `"62eafdaf29dce1d40603d38c3a394f150b98f686"` | `"ac9f533822576170ac2f1b6bf25f66ce22a25033"` |
| output_root | `"C:\\Users\\howar\\.codex\\worktrees\\b06-engineering-bindings\\lightyear-carddemo-modernization\\work\\b06-engineering"` | `"C:/Users/howar/lightyear-b06/oct13-pm/b06-engineering"` |
| replaces | `null` | `{"reason": "local assets and authority destroyed by Codex startup worktree cleanup, 7:19 AM PT; no attempt consumed", "request_content_sha256": "107c20733d9bc7862461b6e13ba4c180cdf1dad160f51be410c5523587900f35"}` |

## Unchanged bindings

| Item | Status | SHA-256 | Basis |
| --- | --- | --- | --- |
| observer_source_sha256 | unchanged | `6420e836dcf69eb433cfab6beafaeca237ae1f3e0dcf48a05a4b16cb92246bac` | bound SHA-256 |
| observer_source_baseline_sha256 | unchanged | `02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b` | bound SHA-256 |
| mirror_adapter_source_sha256 | unchanged | `1f3de745c960e4e9451c382705ea848859df264e8e61c52d4640b93dcac5aa0b` | bound SHA-256 |
| observer_class_files_sha256 | unchanged | `0f4ab8b155163b88db0ac9a1ea5c5884cb8ba116ad178aed452a5ab1b2f4455f` | canonical field JSON |
| host_memory_validation | unchanged | `8f693321471b0ba88107d7000a6b6205770890c1f53294eedb4a969b74f16e7d` | canonical field JSON |
| host_witness_validation_sha256 | unchanged | `8f693321471b0ba88107d7000a6b6205770890c1f53294eedb4a969b74f16e7d` | bound SHA-256 |
| cap_projection_sha256 | unchanged | `51270485be04d66513c2f47c23227e64d8f42936663a334b1e40807ad137b296` | bound SHA-256 |
| attempt_limits | unchanged | `5e0ada26223706d7ce99d4f29766c3157ac85cb20578f660443e4c12f61758e3` | canonical field JSON |
| limits | unchanged | `0a78ca5f25f5cda2ed32fffafb99b7dfa15a0b451dee6b29ff9a36c5f8e30bb1` | canonical field JSON |
| cause_identified_criteria | unchanged | `a76d92cf3527966526f875b77c48f9cc71f870756dbc4cc4e43c1baa934e0498` | canonical field JSON |
| observer_configuration | unchanged | `b71d0250fde5cb0010f721d24c5127c0cc2808a27077673f74ef36a3debef9f8` | canonical field JSON |
| memory_gate | unchanged | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` | canonical field JSON |
| image | unchanged | `f8cd01054c6a61d3e3742091c6599a0729a377a896749e3886f5669155c894f5` | canonical field JSON |
| attempt_modes | unchanged | `5bd204dfa18d90bf20d251444924bbcd9c77302f7f87ce2ee79c0e4b891db2bd` | canonical field JSON |
| scope | unchanged | `011561004e658620cf58cc042407ae90ed68b5a2abf80b89da9425b31849f59b` | canonical field JSON |
| class_input_witness_policy | unchanged | `d4750bd0001939565a7a54cd98723e7bbb881e74385807b96a60d2c0aed41a55` | canonical field JSON |
| no_automatic_retries | unchanged | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` | canonical field JSON |
| no_degradation | unchanged | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` | canonical field JSON |
| stop_after_two | unchanged | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` | canonical field JSON |
| model_calls | unchanged | `5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9` | canonical field JSON |
| qualification_credit | unchanged | `fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa` | canonical field JSON |
| measurement_credit | unchanged | `fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa` | canonical field JSON |
| lightyear/observer/BoundedJdiMirrors.class | unchanged | `2765b6bf3b38f1beddfac6eac1eacd2804bc48f92bc262a363888dfb1f2b48bc` | class bytes |
| lightyear/observer/PostingObserver$1.class | unchanged | `e856c0fc91725bd0428f9f8bf2f6738dd4b3a67afdde2a86bce440063a615e4f` | class bytes |
| lightyear/observer/PostingObserver$Call.class | unchanged | `b67417daefe359892d05db69f9e2320e1d43c56335bc367ad0eff1817907ea71` | class bytes |
| lightyear/observer/PostingObserver$DefinitionIndex$1.class | unchanged | `d0be0c08a4c10a0da516724c3c11ccd3c25f273a7c7947243659dbe442b35b79` | class bytes |
| lightyear/observer/PostingObserver$DefinitionIndex.class | unchanged | `eae23423f17251c26cff23a8debf61620a64b6fef9377587893bf930d125e39a` | class bytes |
| lightyear/observer/PostingObserver$DiagnosticDictionary.class | unchanged | `9eeb1b0a00ba6d25cf5d60c33d57f396677c8b2102a415a501653a28cdcc05d2` | class bytes |
| lightyear/observer/PostingObserver$Generation$ReturnArm.class | unchanged | `52b245343a0232d4135bc40fbfc5545137abe436c07c1985a83297aa4b58a223` | class bytes |
| lightyear/observer/PostingObserver$Generation.class | unchanged | `47224a9057a05cccddac5ad08066ae82c3afd76e3c10365f6d45a2434c7fd0f6` | class bytes |
| lightyear/observer/PostingObserver$GenerationCatch.class | unchanged | `cb0cc55be05b55cf9ca2e7678c331dc300f6d8e20071a3f3e3d7a3ad0ff8996c` | class bytes |
| lightyear/observer/PostingObserver$PendingEntry.class | unchanged | `7f7d25dfb69dcfe93078d338c4cf0f1bdc71c54972c44c321c2c987329018f31` | class bytes |
| lightyear/observer/PostingObserver$PendingPool.class | unchanged | `a3cd895fad478289564d1aa91cba6cacafc34a3bd317eea153a2a18583fd4980` | class bytes |
| lightyear/observer/PostingObserver$PendingSnapshot.class | unchanged | `135300ca4fdcad33c182f76596bc2af748b3f0d0bea8dc264da37c9afeb449ff` | class bytes |
| lightyear/observer/PostingObserver$PendingWitness.class | unchanged | `9fecb8c779b4a4e81c9cafed69719e8df04aeff2de41a2f6aa3d294d35c15a17` | class bytes |
| lightyear/observer/PostingObserver.class | unchanged | `d9292e3b389e0d73aa7aa2c1925f84f19e15f2503c78cb49bddce2dd22d79330` | class bytes |
| image/application | unchanged | `554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268` | image identity pin; presence currently unverified |
| image/oracle | unchanged | `f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300` | image identity pin; presence currently unverified |
| image/support | unchanged | `96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7` | image identity pin; presence currently unverified |

The rule requiring the old template seal is superseded only for the two approved Python-file hash entries, by Howard's explicit approval. The original recovered template/index and old source bytes remain preserved.

## Readiness limits

Four-hour review guard unchanged. This delivery is before 10 AM PDT, leaving at least four hours before 2 PM. Free host memory was 5.95 GiB at 9:11 AM (minimum 30 GiB before launch); Docker Linux-engine pipe was unavailable, so image presence and live overlap are unknown. Disk was 627.84 GiB. Current verdict: NOT READY.

Public fingerprint: `6d4083d20e5d17e5d3be07dd660621f913cfd50da60c68a361fe628565f7aa7f`. Old 4ce00cfa... authority is recorded lost/unrecoverable/never used and rejected as engineering authority. No operational private key was read or used to sign.

All merges remain held. Fallback 4-7 PM requires Howard's explicit selection, changed window and re-sealed request before another exact go. No automatic second attempt or retry.
