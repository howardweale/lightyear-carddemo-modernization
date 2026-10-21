# Generated current status

Change input records or `tools/build_factory_current_status.py` in pull requests.
Do not include `docs/factory/current-status.json` or `current-status.md` in a human
PR. `required-ci` rejects those paths, including deletion/rename, except for a
status-only PR from the verified same-repository GitHub Actions bot, targeting
main on its exact source-named `codex/status-rebuild-<40-character SHA>` branch.

PR verification renders disposable outputs before checking freshness and sealed
inputs. These workspace outputs are not committed. Historical dated records and
input-seal checks are unchanged. POSTTRAN independent-plan CI uses the existing
capture/finish baseline guard around its original tests and freshness check.
Any mutation of the generated baseline, inputs, evidence or index still fails.

After an approved merge, `rebuild-main-status.yml` renders current main and
creates one status-only **draft PR** when bytes changed. It never pushes to main,
approves workflows or reviews, enables auto-merge, or merges. Main protection and
Howard's exact-final-head approval still apply. The workflow needs repository
permission for Actions to create PRs; its default token permissions stay read-only,
with contents and pull-request write permissions scoped to this publication job.

GitHub-token-created PR workflows require a maintainer to select **Approve
workflows to run** in the PR. Draft creation is not CI success or deployment
acceptance. See [GitHub's workflow trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
Review every applicable check on the exact head before requesting merge approval.

The bot counts all open PRs and defers at six. It also defers while an existing
status PR is open, leaving that branch and any human edits untouched. It checks
capacity again before pushing and before creating a PR. Concurrent independent
PR creators can still race the API snapshots; the limit is not an atomic GitHub
reservation. Writers within this workflow are serialized.

Branches are source-bound and never force-pushed, reset or reused after a closed
PR. A main advance or ambiguous publication fails visibly; inspect any existing
branch/PR before recovery. After capacity is available, or after reviewing a
stale proposal, dispatch the workflow on main to render current inputs. The bot
does not integrate main into existing proposals automatically.

Output-only main pushes do not trigger another rebuild. CI-only fixtures cover
the protected-main path, exact output scope, capacity, ownership, stale-source
and ambiguous-write refusals. Deployment acceptance remains separate: observe
the draft, approve its CI, review the final head and obtain Howard's merge
approval before accepting a status commit on main.
