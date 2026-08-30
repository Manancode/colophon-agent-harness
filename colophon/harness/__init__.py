"""The design harness — a bounded loop that repairs a spec until it ships.

This is Phase 5 of the generator. The deterministic gates (Phases 2-4) decide
*whether* a video may ship; the harness decides *what to do when they say no*.
See :mod:`colophon.harness.designer` for the mechanism and a plain-English
explanation of how each problem is routed to the cheapest fix that can solve it.
"""
