# B06 offline integration r5

Operator review; not independent attestation. Zero Docker commands, native pairs and model calls in this increment. B05, work/ms94, template-r1 and J1 predicates are unchanged.

## Completed offline checks

- J1 test connects authenticated synthetic observer streams for both engine formats to the actual paired closed projection, signed zero-model inbox and independent replay. Candidate runtime exceptions use the B05 field shape and bypass the analyst; support/outside origins produce an empty payload and equipment suspicion. This is an offline integration test, not native qualification or an actual builder invocation.
- A synthetic v2 Windows record passes builder_gate and Controller.launch; callback booleans do not replace the signed-record gate.
- Native mutation/evidence-boundary integration preserves original captures. Empty runtime feedback now has an actual signed projection and replay record, rather than inferring successful replay from an absent inbox.
- Posting attribution now requires the failed terminal to name the same exception object and thread as the support unwind. Closed document labels come from independently captured new document/type rows, not a candidate trace. Offline tests connect both-engine cause derivation to the signed inbox and delivery replay, and reject changed roots, threads, origins, documents and engine disagreement. Native qualification remains outstanding.
- The group finalizer uses bounded host subprocesses for native work and archive/replay under one finalization-inclusive deadline. It stops before another slot, signs and announces unexpected results before replay, checks actual cleanup before and after replay, and records attempted/unfinalized/unstarted slots separately. Recovery is limited to the exact authorized run and is charged outside valid trial time. This driver remains unqualified.
- Container window 3 is explained in the offline-catalog-r4 README. Its original evidence is unchanged. Compile-worker hash and final-result checks now raise explicitly under Python optimization.
- 108 B06 offline tests passed on Windows. Tests substitute native boundaries; no tests ran Docker or models. Repository CI is tracked on PR #255.

## Classpath finding — executable freeze blocked

The saved extraction inventories bytes but did not capture the resolved Tycho/Surefire/OSGi test classpath. Howard confirmed no saved classpath is available. Consequently no loaded JUnit copy is claimed. Obtaining that evidence from the pinned image would require a separately approved Docker run; none was run or authorized here.

Class inventory content hash: `6d1fd2ee75da0edb989f445de969cfa038f347f56d36937548137210629f9f56`. The JSON lists all copies, including identical ones.

| Class | Application SHA-256 | Different Maven-cache copies |
|---|---|---|
| org.compiere.acct.Doc | `ef54332a50ce9196612d64dbdd25747f843bc4fcae8925adc425e08d31ef97b1` | 0 |
| org.compiere.acct.DocManager | `2b0cf9982df4de9a2f57923d11612225a006087d48377042bb673251f689ca59` | 0 |
| org.compiere.model.PO | `1dc95fe1a0282c2ef1552cd33403acaf857033dbdfda14883da2ca14e016920a` | 0 |
| org.compiere.util.DB | `b0ece1362b62ba035c3d9f816b8574b366099d18d149af33240d17319a7c1f3c` | 0 |
| org.junit.platform.engine.support.hierarchical.NodeTestTask | `b8f75cb129bd7c932fc226edfb520335d34cbce6ae659337238918fe4f2b862c` | 7 |
| org.junit.platform.launcher.core.ExecutionListenerAdapter | `37ffa222eacc16555002cfe2119b38f44b46aa9eefe935af57ab490e64a912ec` | 10 |

### org.junit.platform.engine.support.hierarchical.NodeTestTask

- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit54/4.0.8/org.eclipse.tycho.surefire.junit54-4.0.8.jar` — `6923581afb7d5cc03224035c869687997f889d6365edc18ed5a814000ceb1796`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit55/4.0.8/org.eclipse.tycho.surefire.junit55-4.0.8.jar` — `6923581afb7d5cc03224035c869687997f889d6365edc18ed5a814000ceb1796`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit56/4.0.8/org.eclipse.tycho.surefire.junit56-4.0.8.jar` — `6923581afb7d5cc03224035c869687997f889d6365edc18ed5a814000ceb1796`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit57/4.0.8/org.eclipse.tycho.surefire.junit57-4.0.8.jar` — `cb03d4171966da07f870c843fc07b7e2500edb15fb1b5451b47a6045910e51ac`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit57withvintage/4.0.8/org.eclipse.tycho.surefire.junit57withvintage-4.0.8.jar` — `cb03d4171966da07f870c843fc07b7e2500edb15fb1b5451b47a6045910e51ac`
- `/root/.m2/repository/org/junit/platform/junit-platform-engine/1.12.2/junit-platform-engine-1.12.2.jar` — `28a34f34198c18f7e734b1c0bf45f22afa5982ce462652cb1907120986414517`
- `/root/.m2/repository/org/junit/platform/junit-platform-engine/6.0.3/junit-platform-engine-6.0.3.jar` — `df23a4b25bb26e63d95887ff230f65de57ab4665ae196a8fc087f4eae571c645`

### org.junit.platform.launcher.core.ExecutionListenerAdapter

- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit5/4.0.8/org.eclipse.tycho.surefire.junit5-4.0.8.jar` — `171519a846d6cf3b70470ab4bbf71315ee9132be5451975e474016692d4dda0b`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit54/4.0.8/org.eclipse.tycho.surefire.junit54-4.0.8.jar` — `b992b7a452728fa316b499b5418a0b03e9401b2c4cef17cfbd565ebfd5dda2fb`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit55/4.0.8/org.eclipse.tycho.surefire.junit55-4.0.8.jar` — `b992b7a452728fa316b499b5418a0b03e9401b2c4cef17cfbd565ebfd5dda2fb`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit56/4.0.8/org.eclipse.tycho.surefire.junit56-4.0.8.jar` — `b992b7a452728fa316b499b5418a0b03e9401b2c4cef17cfbd565ebfd5dda2fb`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit57/4.0.8/org.eclipse.tycho.surefire.junit57-4.0.8.jar` — `b992b7a452728fa316b499b5418a0b03e9401b2c4cef17cfbd565ebfd5dda2fb`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit57withvintage/4.0.8/org.eclipse.tycho.surefire.junit57withvintage-4.0.8.jar` — `b992b7a452728fa316b499b5418a0b03e9401b2c4cef17cfbd565ebfd5dda2fb`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit58/4.0.8/org.eclipse.tycho.surefire.junit58-4.0.8.jar` — `cbce95066b3b2dbea20c1aea5027dd54fbe87ce2bcd13b718aca45c7e8042dcc`
- `/root/.m2/repository/org/eclipse/tycho/org.eclipse.tycho.surefire.junit58withvintage/4.0.8/org.eclipse.tycho.surefire.junit58withvintage-4.0.8.jar` — `cbce95066b3b2dbea20c1aea5027dd54fbe87ce2bcd13b718aca45c7e8042dcc`
- `/root/.m2/repository/org/junit/platform/junit-platform-launcher/1.12.2/junit-platform-launcher-1.12.2.jar` — `2df8ab41ee7126239049ebf05dbe6d9c792de9cf5e02f78c3b28ed53462775b8`
- `/root/.m2/repository/org/junit/platform/junit-platform-launcher/6.0.3/junit-platform-launcher-6.0.3.jar` — `79cc473f4afc006566830911a61d70a78e18cc636a80398c68a85182c5f4957c`

## Revised assemblies, not executable plans

All four source corrections from the signed offline-catalog-r4 summary are bound in the new J1 schedule. J2/J3 have no affected source, and bind the same preparation summary plus their compiled source catalog hashes. Original schedules remain unchanged. No native slot has run.

| Journey | Slots | Assembly content SHA-256 | Estimated serial Docker hours |
|---|---:|---|---|
| J1 | 55 | `5d876f692f263082bf78d410fffc576311dbea83ce2c679a9e45ea21a9164507` | 9.17–18.33 |
| J2 | 41 | `124bd9f11b15dd0255359e03e3bf41de6cdda99bce56d0b548f8c74f1b687f4a` | 6.83–13.67 |
| J3 | 39 | `dd3ce3bcd549869cf030fd9d6f4308894df048976f7c82f904abd1151107ef89` | 6.5–13.0 |

These are deliberately blocked assembly specifications. No executable snapshot hash or approval-ready native plan is issued. Besides classpath resolution, complete private per-slot input assembly remains unsealed. Posting-cause projection/delivery is now connected and tested offline, but has no native qualification credit. The finalizer refuses to credit missing posting replay.

Before any outcome, the revised J1 assembly explicitly records empty feedback and equipment suspicion for `duplicate-trace-key`: the bound candidate misuses `JourneySupport.fact`, and the throw originates in support. The exact duplicate-key negative check must still replay; an arbitrary execution failure cannot pass. This changes no J1 predicate. Earlier draft hashes remain in Git history; none was frozen or run.

Core-status items 1–2: additional offline integration, no native qualification. Item 3: four source revisions bound; executable assembly blocked as above. Item 4: host-denial admission tested, Codex process proof is a separate increment. Item 5: complete executable preflight remains outstanding.

Next approval must bind exact executable plan commits and each journey’s Docker window after these blockers close. The prior proposed windows are historical planning fields, not authority to execute. No qualification or measurement launch is authorized.
