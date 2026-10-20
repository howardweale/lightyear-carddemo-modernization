# Generated current status

Change input records or `tools/build_factory_current_status.py` in pull requests.
Do not include `docs/factory/current-status.json` or `current-status.md` in a PR.
`required-ci` rejects those output paths, including deletion/rename, except for a
status-only PR from the verified same-repository GitHub Actions bot.

PR verification renders disposable outputs before checking freshness and sealed
inputs. These workspace outputs are not committed. Historical dated records and
input-seal checks are unchanged.

After an approved merge, `rebuild-main-status.yml` renders the latest main and
makes one `status: rebuild after <source SHA>` bot commit only when bytes changed.
It stages only the two output files, serializes writers, and regenerates after
concurrent main advances. It never force-pushes. Output-only pushes do not trigger
the rebuild workflow. The job uses its repository GITHUB_TOKEN; it does not alter
branch protection or request a new secret. A protected-branch denial fails the
job visibly instead of bypassing repository policy.

CI fixtures cover PR refusal and bounded bot behavior. Deployment acceptance is
separate: after this workflow is merged with approval, an input-changing merge
must produce one observed bot status commit, and an unchanged render none.
