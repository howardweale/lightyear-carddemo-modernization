# Retained Linux JDK alternatives — 2026-10-11

The exact JDK exported from retained image `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268` is **Temurin 21.0.10+7 for Linux amd64**. The prior host baseline was Windows Corretto 21.0.10+7. This closes the substituted-JDK limitation for the synthetic matrix, not the native J1 evidence gap.

[Hash/count receipt](b06-retained-jdk-alternatives.json) binds the image manifest, all14 exported compressed layers, 2,323,025,920-byte archive, exact java binary, public fixture/counter, training trace, CDS archive, linked image and dumps. Export command:

```text
docker image save --output work/retained-jdk-export-r1/image.tar sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268
```

Before export the previous B06 controller had exited, its signed terminal report was preserved, both launcher PIDs were absent and the `lightyear.journey` container inventory was empty. No evidence window was active. Only `opt/java/openjdk` was extracted; no image configuration/environment, application files or credentials were extracted. No container was created or started, no image was pulled and no network operation occurred during export/extraction. WSL's existing Ubuntu host executed public synthetic Java; JDI connected locally to its synthetic child. The exported image/JDK/classes and raw dumps stay local.

## Same 24-iteration fixture, three repetitions

| Variant | Linux generation calls | Windows generation calls | Linux median wall ms | Windows median wall ms |
|---|---:|---:|---:|---:|
| Installed baseline |240|240|67.389|97.345|
| Matched jlink control |388|388|95.710|168.070|
| Trained JLI |196|196|72.797|114.556|
| Dynamic CDS |171|171|58.357|97.174|

Every repetition completed. Timings are separate executions without JDI attached; counts come from separate entry-only JDI runs. Trained JLI reduced watched entries49.485% against the module-identical control. CDS reduced them28.75% against the installed baseline. Outer `spinInnerClass` entries stayed25 in every configuration. Neither optimization removes the observer's entry/return correctness obligation. Training uses the public fixture only; no J1-trained runtime exists yet. The Linux linked image is59,783,056bytes and CDS archive544,768bytes. Raw samples and aggregate manifests are in the receipt. Three samples do not establish a production speedup; cross-OS/vendor timing differences are not a controlled comparison.

## Dump coverage and cost

| Dump setting | Files | Bytes | Linux median ms | Added time vs baseline |
|---|---:|---:|---:|---:|
| MethodHandle internals |83|123,886|92.764|37.65%|
| Lookup hidden definitions |24|8,472|67.353|-0.05% (noise) |
| Lambda proxies |25|7,000|71.509|6.12%|
| All settings |132|139,358|100.481|49.10%|

Counts and bytes match the Windows experiment. Names identify the JDK emitter family, not authenticated caller provenance. Lookup covers the fixture's24 direct hidden definitions, including their bytes; the fixture's24 ordinary `ClassLoader.defineClass` operations produce no additional separate dumps under these settings. Ordinary and hidden fixture definitions intentionally share input bytes, so byte equality cannot establish which call supplied a dump. These facilities supplement diagnostics; they do not provide complete hidden-class attribution, a global generation census, or a replacement evidence contract.

The current native hold stays in force. [Contingent count-only proposal](b06-count-only-contingent-request.md) is prepared and unsubmitted. Its prerequisite is a Part6 report explicitly concluding that no cause was identified under Howard's narrow criterion. An actual cause blocks this proposal. No qualification or measurement credit, model call or native application run occurred here.
