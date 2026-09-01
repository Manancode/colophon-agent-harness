---
layout: post
title: "We open-sourced our launch-video harness"
date: 2026-09-01
author: launch-video
---

Listen. I finally did the thing I kept putting off — I open-sourced the launch-video harness.

It started because I ship stuff (RankPal, mostly) and the launch video was always the part I dreaded. You know how it goes. You finish the product, you're tired, and the video is either a Fiverr invoice or a 2am hack you'll never be able to repeat.

So I built a harness that uses my own coding agent as the brain. No LLM key of mine, no server in the middle. You give it a brief, it routes to a local render engine, it renders, and then — and this is the bit I'm proud of — it grades its own work before it's allowed to call it done.

Eight dimensions. Hook, capability, brand, motion, narration, subtitles, CTA, length. Everything under a 4 out of 5 gets sent back to fix that one thing. No averaging your way past a failure, and no "looks fine to me" — every score has to point at evidence.

I also locked two things in from the start because they matter to me: telemetry stays off (nothing leaves the machine) and we don't add new API keys for marginal gains.

The repo is the method and the gate, not the engines — those are separate local tools. If you've ever stared at a blank timeline wondering why this is so hard, go look. Maybe it saves you the 2am version.
