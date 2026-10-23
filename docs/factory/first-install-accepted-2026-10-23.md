# Factory Tower first installation accepted

Recorded 2026-10-23. Howard accepted the new installation and published its public trust values on [PR #415](https://github.com/howardweale/lightyear-carddemo-modernization/pull/415#issuecomment-6368416273). This record adds current installation evidence beside the [MS-106 correction](first-install-2026-10-21/ms106-correction.md); it does not rewrite that correction or substantiate the earlier October 14 deployment claims.

The installed reviewed source is `2a82934b47f3a5953e266c683f60c25f4ecfb517`, with bundle manifest SHA-256 `3b68c83ce45de2b1251d4d648ec1506de318a9bd01b54f0e1e4f462d230e25b0`. The reviewed bundle is [reviewed in the installation CI run](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/39682920021/artifacts/12384763102).

After Howard signed out and back in without manually starting Tower, the enabled `Lightyear-FactoryTower-Howard` task ran at 08:18:46 Pacific on October 23, and its process started at 08:19:09. Both belong to `POWDERSNOW\howar`, SID `S-1-5-21-3687384130-2006818898-1210227752-1001`. The task uses Interactive logon, Limited privileges and that account's login trigger. Read-only inspection found exactly one listener, on `127.0.0.1:8769`.

The user-level signed-only environment setting and referenced configuration file were present after sign-in. Presence alone is not a fresh cryptographic consumer-verification result; no backfill proof is included here.

The posted PEM's exact ASCII bytes, including LF after its END line, hash to `658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a`. The posted journal head is `568c8f8330ddec00b05d27c0c64a84a0208daaae0ec004e96aaa877191f33218`. The adjacent JSON retains the public PEM and byte count. These values come exclusively from Howard's public comment; no local authority files or proof endpoint were read for this record.

The journal head is the posted observation, not an indefinitely current value. New-key POSTTRAN preparation and the first COPAU request remain separate work. This record grants no signing, model spending, execution or release authority.
