# ChatGPT-only Frontend Architecture

The user-facing surface is ChatGPT only.

## Cloud backend
GitHub Actions performs data sync, research discovery, feature generation, model evaluation, recommendation, review, and persistent state updates. It does not publish a human-facing dashboard.

## Bridge
After every cloud cycle, `chatgpt_bridge.py` writes machine-readable JSON files under `bridge/`:
- `bridge/latest.json`
- `bridge/ssq.json`
- `bridge/dlt.json`
- `bridge/review.json`
- `bridge/research.json`

These files are intended for ChatGPT scheduled tasks to read from a single current `main` commit, preferably through the authenticated GitHub connector. Resolve the commit once and use that ref for both files so a concurrent state commit cannot mix snapshots. The user does not need to open them.

The recommendation contract separates two questions:
- `bridge_health` describes the backend snapshot and operational warnings.
- `publication` in a lottery file, mirrored by `publications[lottery]` in `latest.json`, describes whether that immutable frozen recommendation is eligible for publication.

An old backend-run timestamp does not alone invalidate a verified same-day freeze. For example, a 14:06 freeze can be published at16:03 when its publication checks pass and its validity window has not expired; requiring a run after15:30 is an invented restriction. Conversely, a fresh bridge cannot make an old, invalid, already drawn, suspended, or unverified recommendation publishable.

## ChatGPT frontend
ChatGPT scheduled tasks should run after the backend cycle, fetch the relevant bridge JSON, and present:
- draw-day recommendation in ChatGPT
- post-draw review in ChatGPT
- meaningful research/model changes in ChatGPT

For SSQ use [the saved task prompt](CHATGPT_SSQ_TASK_PROMPT.md). A `READY` result still requires matching payloads, today's Beijing target date, the publication window and formal-record fields. Non-READY results are reported as their specific cause, without generating numbers or substituting a previous draw. Unrelated research/DLT partial failures and primary-source403 warnings remain visible without being misreported as missing SSQ output.

## Delivery identity and acknowledgement

The publication carries a stable draw identity (`target_issue_key`, currently a next-after-basis identity where the official target issue has not yet been observed), `prediction_id`, `freeze_sha256`, and `dedupe_key`. Preserve these fields in every formal ChatGPT output. Suppress repeat delivery for the same issue identity or prediction ID, and flag conflicting records for an issue rather than delivering a second set.

Consult previous formal delivery outputs, not `recent_reviews`; a review proves scoring, not delivery. If delivery history cannot be read, report unknown deduplication state and do not fabricate a receipt. A ChatGPT output marker is an auditable conversational receipt, but there is no atomic transaction spanning GitHub and ChatGPT message delivery. Strict exactly-once delivery requires a delivery adapter that can reconcile provider message IDs with a persistent acknowledgement ledger; it cannot be claimed from bridge generation or prompt changes alone.

User feedback remains conversational in ChatGPT. Proposed changes are treated as research hypotheses/configuration requests and are folded into the next model-development cycle rather than bypassing validation.

## Timing (Beijing time)
- Cloud backend: 08:37 preparation; 12:07,14:07,14:37,15:07,15:30,15:45 retries; 18:45 recovery; 23:07,23:37 review. See GITHUB_ACTIONS_DEPLOY.md; scheduling is best effort.
- ChatGPT frontend: 09:00 research digest when meaningful / 16:00 draw-day recommendation / 23:20 review when a new draw exists

## Security / visibility
No GitHub Pages site is required. A public repository is the simplest zero-cost bridge because ChatGPT can read raw JSON without an authenticated GitHub connector. If the repository is private, an authenticated bridge is required and cannot be read by ordinary public web retrieval.
