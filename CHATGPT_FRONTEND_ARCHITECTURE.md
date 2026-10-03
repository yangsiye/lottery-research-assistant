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

These files are intended for ChatGPT scheduled tasks to read from the repository's raw-content URL. The user does not need to open them.

## ChatGPT frontend
ChatGPT scheduled tasks should run after the backend cycle, fetch the relevant bridge JSON, and present:
- draw-day recommendation in ChatGPT
- post-draw review in ChatGPT
- meaningful research/model changes in ChatGPT

User feedback remains conversational in ChatGPT. Proposed changes are treated as research hypotheses/configuration requests and are folded into the next model-development cycle rather than bypassing validation.

## Timing (Beijing time)
- Cloud backend: 08:30 / 15:30 / 23:00
- ChatGPT frontend: 09:00 research digest when meaningful / 16:00 draw-day recommendation / 23:20 review when a new draw exists

## Security / visibility
No GitHub Pages site is required. A public repository is the simplest zero-cost bridge because ChatGPT can read raw JSON without an authenticated GitHub connector. If the repository is private, an authenticated bridge is required and cannot be read by ordinary public web retrieval.
