# launch-video

A harness that turns a product-launch brief into a finished launch video — using your own coding agent as the brain. No LLM key, no server of ours.

I built this because every time I shipped something (RankPal, my App Store publishing app), the launch video was the part that fell through the cracks. Either I paid someone, or I hacked together something at 2am that I couldn't reproduce.

So I made a thing that does the boring parts for me:

- You hand it a brief ("make me a 20-second launch video for RankPal").
- It figures out which kind of video that is and routes to a local, key-free render engine.
- It renders.
- Then it grades its own work against a review gate before it lets me call it done.

That last part is the whole point. The gate has eight dimensions — hook, capability accuracy, brand consistency, motion, narration, subtitles, CTA, length. Every one has to score at least a 4 out of 5, backed by real evidence (pixel samples, media probes, source checks), not "looks good to me." If something's under 4, it goes back and fixes that one thing. No averaging your way past a failure.

Two rules I baked in from day one, because they matter to me:

- **Telemetry stays off.** Nothing leaves the machine.
- **No new API keys.** If a feature needs a key I don't already have, it doesn't get added.

That's it. `SKILL.md` is the brain, `RUNBOOK.md` is how I finished the first end-to-end test, and `review/` is the gate plus the scorecards from when I ran it for real.
