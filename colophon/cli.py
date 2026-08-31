"""The ``colophon`` command line.

Pipeline:

    doctor    check the runtime
    init      freeze a spec into a new run
    plan      lay the scenes onto the clock
    validate  spec + timeline, no rendering
    emit      spec -> editable video project
    render    project -> MP4
    qa        run the deterministic stage pipeline
    review    extract frames + contact sheet, bind the review context
    record-review  validate an independent review, merge with the gates
    repair    apply targeted spec ops
    design    run the repair loop on a spec (mechanical fixes; --render also drives the renderer)
    deliver   everything above, end to end
    resume    continue from the last attempt that matches the frozen spec
    bench     compare harnesses on known-good and known-bad artifacts
    mcp       expose colophon as MCP tools over HTTP (for an agent harness)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .presentation.normalize import normalize
from .qa import runner as qa_runner
from .qa import eval_protocol as eval_protocol
from .qa import taxonomy as taxonomy
from .qa.runner import format_report
from .qa.stages import grounding as grounding_stage
from .qa.stages import media as media_stage
from .qa.stages import spec as spec_stage
from .qa.stages import static as static_stage
from .qa.stages import structure as structure_stage
from .qa.stages import taste as taste_stage
from .qa.stages import delivery as delivery_stage
from .qa.stages import motion_velocity as motion_velocity_stage
from .qa.rubric import rubric_markdown
from .renderers.base import get_adapter
from .review import extract as review_extract
from .review import context as review_context
from .review import critics as review_critics
from .qa.taxonomy import Assessment, Finding, Severity
from .runs import layout as run_layout
from .runs import manifest as run_manifest
from .runtime import tools
from .spec.hash import sha256_file, spec_sha256
from .spec.io import load as load_spec
from .spec.io import write_json
from .spec.schema import VideoSpec
from .timeline.plan import build_plan
from .harness import designer as harness_designer  # Phase 5 design-harness loop
from .harness import orchestrator as harness_orchestrator  # Phase 6 render-aware loop
from .bench import harness_matrix  # Phase 7 external bench
from .bench.harness_matrix import format_matrix
from . import mcp_server  # MCP tool surface (TrueForge integration)

DEFAULT_RENDERER = "hyperframes"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _log(message: str) -> None:
    print(message, flush=True)


def _fail(message: str, code: int = 1) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def _render_failure(result) -> int:
    """Report a failed render completely, then fail.

    Previously this printed ``render_result.stderr`` alone, and the render we
    were trying to debug produced a literally empty error line. Never reduce a
    failure to one stream: use every fact the result carries.
    """
    _log("  render failed:")
    _log(f"  {result.describe_failure()}")
    _log(f"  command: {' '.join(str(c) for c in result.command)}")
    return _fail("render failed")


def _spec_for(run_dir: Path) -> VideoSpec:
    paths = run_layout.run_paths(run_dir)
    if not paths.spec.is_file():
        raise SystemExit(f"no spec at {paths.spec}; run `colophon init` first")
    return load_spec(paths.spec)


def _plan_for(spec: VideoSpec):
    normalized_spec, log = normalize(spec)
    plan = build_plan(normalized_spec)
    return normalized_spec, plan, log


def _evaluable_attempt(paths, spec: VideoSpec, number: int | None) -> int | None:
    """The attempt an evaluation command may honestly report on, or None.

    Shared by ``qa``, ``review`` and ``record-review`` so all three refuse a
    stale attempt the same way, rather than each command growing its own idea
    of "latest". An attempt emitted from an older spec is not a candidate:
    its project and video were made by something else, and a report carrying
    today's hash would describe artifacts that hash never produced.

    Returns ``None`` having printed the reason, which is the same contract the
    callers already use for "nothing to do, fail".
    """
    try:
        return run_manifest.evaluable_attempt(paths, spec_sha256(spec), number)
    except (FileNotFoundError, run_manifest.StaleArtifactError) as exc:
        _fail(str(exc))
        return None


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    _log("Resolving runtime tools…")
    found = tools.resolve_runtime()
    for name in sorted(found):
        t = found[name]
        status = f"{t.version or '?'}  {t.path}" if t.found else "MISSING"
        _log(f"  {name:<10} {status}")
    key = tools.cache_key(found)
    _log(f"  cache_key {key}")

    ok = all(t.found for t in found.values())
    if args.run_dir:
        paths = run_layout.run_paths(args.run_dir)
        write_json(
            {
                "tools": {k: v.to_dict() for k, v in found.items()},
                "cache_key": key,
                "ready": ok,
            },
            paths.runtime_state,
        )
        _log(f"  wrote {paths.runtime_state}")
    return 0 if ok else 1


def cmd_init(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    spec, log = normalize(spec)
    try:
        paths = run_layout.init_run(args.run_dir, spec)
    except FileExistsError as exc:
        return _fail(str(exc))
    _log(f"Run initialised at {paths.root}")
    _log(f"  spec sha256 {spec_sha256(spec)}")
    _log(f"  {len(spec.scenes)} scenes, {len(spec.claims)} claims")
    for entry in log.entries:
        _log(f"  normalize: {entry['scene_id']} {entry['action']} {entry['detail']}")
    write_json(
        {"tools": {k: v.to_dict() for k, v in tools.resolve_runtime().items()}},
        paths.runtime_state,
    )
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    out = paths.root / "plan.json"
    write_json(plan.to_dict(), out)
    _log(f"Wrote {out}")
    for w in plan.windows:
        _log(
            f"  {w.scene_id:<20} {w.start_s:>6.2f}s → {w.end_s:>6.2f}s "
            f"({w.duration_frames}f)"
        )
    _log(f"  total {plan.total_duration_s:.2f}s / {plan.total_frames}f @ {plan.fps}fps")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    result = qa_runner.run_stages(
        [spec_stage.spec_validate, spec_stage.timeline_continuity, spec_stage.narrative_order],
        {"spec": spec, "plan": plan},
        spec_sha256=spec_sha256(spec),
    )
    print(format_report(result))
    return 0 if result.passed else 1


def _emit_project(paths, spec, plan, adapter, attempt):
    from .renderers.base import RenderContext

    ctx = RenderContext(
        spec=spec,
        plan=plan,
        project_dir=attempt.project,
        out_dir=attempt.artifact,
    )
    result = adapter.emit(ctx)
    _log(f"  emitted {result.entry} ({len(result.scene_fragments)} scenes)")
    for warning in result.warnings:
        _log(f"  warning: {warning}")
    write_json(result.to_dict(), attempt.qa / "emit.json")
    return result


def cmd_emit(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    adapter = get_adapter(args.renderer)
    attempt = run_layout.begin_attempt(paths, args.attempt)
    _emit_project(paths, spec, plan, adapter, attempt)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    adapter = get_adapter(args.renderer)
    attempt = (
        run_layout.AttemptPaths(
            root=paths.attempts / f"{args.attempt:02d}",
            project=paths.attempts / f"{args.attempt:02d}" / "project",
            artifact=paths.attempts / f"{args.attempt:02d}" / "artifact",
            qa=paths.attempts / f"{args.attempt:02d}" / "qa",
            review=paths.attempts / f"{args.attempt:02d}" / "review",
        )
        if args.attempt
        else None
    )
    if attempt is None:
        number = run_layout.latest_attempt(paths)
        if number is None:
            return _fail("no attempts yet; run `colophon emit` first")
        attempt = run_layout.begin_attempt(paths, number)

    from .renderers.base import RenderContext

    ctx = RenderContext(
        spec=spec, plan=plan, project_dir=attempt.project, out_dir=attempt.artifact
    )
    _log(f"Rendering with {adapter.name}@{adapter.version}…")
    render_result = adapter.render(ctx, None)
    write_json(render_result.to_dict(), attempt.qa / "render.json")
    if not render_result.ok:
        return _render_failure(render_result)
    _log(f"  wrote {render_result.video_path} ({render_result.duration_s:.2f}s)")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    number = _evaluable_attempt(paths, spec, args.attempt)
    if number is None:
        return 1
    attempt = run_layout.begin_attempt(paths, number)

    document = (attempt.project / "index.html").read_text(encoding="utf-8") if (
        attempt.project / "index.html"
    ).is_file() else None
    video = attempt.artifact / "launch-video.mp4"
    emit_info: dict[str, Any] = {}
    if (attempt.qa / "emit.json").is_file():
        emit_info = json.loads((attempt.qa / "emit.json").read_text(encoding="utf-8"))

    result = qa_runner.run_stages(
        [
            spec_stage.spec_validate,
            spec_stage.timeline_continuity,
            spec_stage.narrative_order,
            static_stage.static_html,
            static_stage.canvas_audit,
            structure_stage.scene_structure,
            grounding_stage.claim_grounding,
            taste_stage.ai_slop_detector,
            taste_stage.color_consistency,
            taste_stage.centerpiece_invariant,
            taste_stage.motion_accessibility,
            delivery_stage.delivery_contract,
            motion_velocity_stage.motion_pixel_velocity,
            media_stage.media_contract,
        ],
        {
            "spec": spec,
            "plan": plan,
            "document": document,
            "scene_fragments": emit_info.get("scene_fragments"),
            "video_path": video if video.is_file() else None,
            # Only the missing-asset check needs this; the rest of the gate
            # runs fine before a render.
            "project_dir": attempt.project,
        },
        spec_sha256=spec_sha256(spec),
    )
    print(format_report(result))
    assessment = taxonomy.assess(result.results)
    print(assessment)
    fp = eval_protocol.compute_eval_fingerprint()
    print(eval_protocol.format_eval_fingerprint(fp))
    write_json(
        {
            "eval_fingerprint": fp,
            "assessment": assessment.to_dict(),
            **result.to_dict(),
        },
        attempt.qa / "qa-report.json",
    )
    return 0 if result.passed else 1


def cmd_review(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    number = _evaluable_attempt(paths, spec, args.attempt)
    if number is None:
        return 1
    attempt = run_layout.begin_attempt(paths, number)
    video = attempt.artifact / "launch-video.mp4"
    if not video.is_file():
        return _fail(f"no video at {video}; run `colophon render` first")

    stamps = review_extract.scene_midpoints(plan)
    frames = attempt.review / "frames"
    frameset = review_extract.extract_frames(video, stamps, frames)
    sheet = review_extract.build_contact_sheet(
        frameset, attempt.review / "contact-sheet.png"
    )
    review_extract.write_manifest(frameset, attempt.review / "frames.json")

    # Build the hash-bound review context. Every artifact and preview is
    # hashed here so the independent review that follows is provably a review
    # of THIS attempt -- not last week's video, not a swapped file. The
    # reviewer must copy these hashes back unchanged.
    context = review_context.build_review_context(
        attempt_id=f"{number:02d}",
        spec_sha256=spec_sha256(spec),
        video=video,
        frames=frameset.frames,
        contact_sheet=sheet,
    )
    context_path = review_context.write_review_context(
        context, attempt.review / "review-context.json"
    )
    rubric_path = attempt.review / "rubric.md"
    rubric_path.write_text(rubric_markdown(), encoding="utf-8")

    _log(f"Extracted {len(frameset.frames)} frames to {frames}")
    _log(f"Contact sheet: {sheet}")
    _log("")
    # Spread, not average. A bare canvas reads spread=0 (every pixel is the
    # same pixel); a frame with content reads 100-250 depending on contrast.
    # The average is nearly blind on a dark design: content lifts YAVG by
    # ~1.6 units while it lifts the peak by ~206. The spread moves in both
    # directions, so it works for light-on-dark and dark-on-light designs.
    _log("Frame spread (0 = blank, >8 means content was drawn):")
    for t, stats in zip(frameset.timestamps, review_extract.luma_stats_at(video, stamps)):
        if stats.spread is None:
            shown = "n/a"
        else:
            shown = f"{stats.spread:.0f}"
        _log(f"  t={t:>6.2f}s  spread={shown}")
    _log("")
    _log("Independent visual review:")
    _log(f"  context : {context_path}")
    _log(f"  rubric  : {rubric_path}")
    _log(f"  context hash: {context.review_context_sha256}")
    _log("")
    _log(
        "A fresh reviewer (not the generator) scores the rubric, copies the "
        "context hash and every artifact/preview hash back, and returns the "
        "review JSON. Then:"
    )
    _log(
        f"  colophon record-review {args.run_dir} --attempt {number} "
        "--review review.json"
    )
    return 0


def _assessment_from_qa_report(report: dict) -> Assessment:
    """Rebuild the deterministic verdict from a stored qa-report.json."""
    a = report.get("assessment", {})
    blockers = tuple(
        Finding(
            stage_id=f["stage_id"],
            message=f["message"],
            code=f.get("code"),
            severity=Severity(f["severity"]),
            known=f["known"],
        )
        for f in a.get("blockers", [])
    )
    warnings = tuple(
        Finding(
            stage_id=f["stage_id"],
            message=f["message"],
            code=f.get("code"),
            severity=Severity(f["severity"]),
            known=f["known"],
        )
        for f in a.get("warnings", [])
    )
    return Assessment(a.get("state", "blocked"), blockers, warnings)


def cmd_record_review(args: argparse.Namespace) -> int:
    """Validate an independent review and merge it with the deterministic verdict."""
    paths = run_layout.run_paths(args.run_dir)
    if not paths.spec.is_file():
        return _fail(f"no spec at {paths.spec}; run `colophon init` first")
    spec = load_spec(paths.spec)
    spec, _, _ = _plan_for(spec)
    number = _evaluable_attempt(paths, spec, args.attempt)
    if number is None:
        return 1
    attempt = run_layout.begin_attempt(paths, number)

    context_path = attempt.review / "review-context.json"
    if not context_path.is_file():
        return _fail(f"no review context at {context_path}; run `colophon review` first")

    try:
        context = review_context.read_review_context(context_path)
        review_context.validate_context(context)
    except review_context.ContextError as exc:
        return _fail(f"review context invalid: {exc}")

    qa_report_path = attempt.qa / "qa-report.json"
    if not qa_report_path.is_file():
        return _fail(f"no qa-report.json at {qa_report_path}; run `colophon qa` first")
    deterministic = _assessment_from_qa_report(
        json.loads(qa_report_path.read_text(encoding="utf-8"))
    )

    review_path = Path(args.review)
    if not review_path.is_file():
        return _fail(f"review file not found: {review_path}")
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        validated = review_critics.validate_review(review, context)
    except (ValueError, review_critics.ReviewError) as exc:
        return _fail(f"visual review rejected: {exc}")

    merged = review_critics.merge_verdict(deterministic=deterministic, review=validated)

    record = {
        "attempt_id": context.attempt_id,
        "review_context_sha256": context.review_context_sha256,
        "reviewer": validated.reviewer,
        "reviewer_mode": validated.reviewer_mode,
        "verdict": validated.verdict,
        "score_vector": validated.scores,
        "blockers": list(validated.blockers),
        "merged_assessment": merged.to_dict(),
    }
    write_json(record, attempt.review / "review-record.json")

    _log(f"Reviewer : {validated.reviewer} ({validated.reviewer_mode})")
    _log(f"Verdict  : {validated.verdict}")
    print(merged)
    _log("")
    _log(f"Recorded: {attempt.review / 'review-record.json'}")
    return 0 if merged.shippable else 1


def cmd_repair(args: argparse.Namespace) -> int:
    from .repair.apply import RepairOp, apply_ops

    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    ops = [RepairOp(**op) for op in json.loads(Path(args.ops).read_text(encoding="utf-8"))]
    claim_edits = (
        json.loads(Path(args.claim_edits).read_text(encoding="utf-8"))
        if args.claim_edits
        else None
    )
    result = apply_ops(spec, ops, claim_edits)
    write_json(result.to_dict(), paths.root / "repair.json")
    _log(json.dumps(result.report, indent=2))
    if args.write:
        # writing a new spec means a new run; the old one stays intact
        from .spec.io import save

        save(result.spec, paths.spec.parent / "spec.repaired.json")
        _log(f"Wrote {paths.spec.parent / 'spec.repaired.json'}")
    return 0


def cmd_deliver(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    if not paths.spec.is_file():
        return _fail(f"no spec at {paths.spec}; run `colophon init` first")

    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    digest = spec_sha256(spec)

    adapter = get_adapter(args.renderer)
    number = args.attempt or run_layout.next_attempt(paths)
    attempt = run_layout.begin_attempt(paths, number)
    manifest = run_manifest.new_manifest(
        number, spec, renderer=adapter.name, renderer_version=adapter.version
    )
    _log(f"Attempt {number:02d} — {adapter.name}@{adapter.version}")
    _log(f"  spec {digest}")

    emit_result = _emit_project(paths, spec, plan, adapter, attempt)

    _log("Rendering…")
    from .renderers.base import RenderContext

    ctx = RenderContext(
        spec=spec, plan=plan, project_dir=attempt.project, out_dir=attempt.artifact
    )
    render_result = adapter.render(ctx, emit_result)
    write_json(render_result.to_dict(), attempt.qa / "render.json")
    if not render_result.ok:
        manifest.qa_passed = False
        run_manifest.write_manifest(attempt, manifest)
        return _render_failure(render_result)
    _log(f"  {render_result.video_path} ({render_result.duration_s:.2f}s)")

    _log("QA…")
    document = (attempt.project / "index.html").read_text(encoding="utf-8")
    result = qa_runner.run_stages(
        [
            spec_stage.spec_validate,
            spec_stage.timeline_continuity,
            spec_stage.narrative_order,
            static_stage.static_html,
            static_stage.canvas_audit,
            structure_stage.scene_structure,
            grounding_stage.claim_grounding,
            taste_stage.ai_slop_detector,
            taste_stage.color_consistency,
            taste_stage.centerpiece_invariant,
            taste_stage.motion_accessibility,
            delivery_stage.delivery_contract,
            motion_velocity_stage.motion_pixel_velocity,
            media_stage.media_contract,
        ],
        {
            "spec": spec,
            "plan": plan,
            "document": document,
            "scene_fragments": emit_result.scene_fragments,
            "video_path": render_result.video_path,
            "project_dir": attempt.project,
            # Only cmd_deliver knows this: QA runs after the encode, so the
            # delivery gate can compare the measured artifact against the
            # timeline instead of guessing from the spec. cmd_qa has no
            # artifact and deliberately leaves it out.
            "rendered_duration_s": render_result.duration_s,
        },
        spec_sha256=digest,
    )
    print(format_report(result))
    assessment = taxonomy.assess(result.results)
    print(assessment)
    fp = eval_protocol.compute_eval_fingerprint()
    print(eval_protocol.format_eval_fingerprint(fp))
    write_json(
        {
            "eval_fingerprint": fp,
            "assessment": assessment.to_dict(),
            **result.to_dict(),
        },
        attempt.qa / "qa-report.json",
    )

    from .spec.hash import scene_hashes as _scene_hashes

    review_summary: dict[str, Any] = {"reviewed": False}
    if args.review and render_result.video_path:
        _log("Review package…")
        stamps = review_extract.scene_midpoints(plan)
        frameset = review_extract.extract_frames(
            render_result.video_path, stamps, attempt.review / "frames"
        )
        review_extract.build_contact_sheet(
            frameset, attempt.review / "contact-sheet.png"
        )
        review_extract.write_manifest(frameset, attempt.review / "frames.json")
        luma = review_extract.luminance_at(render_result.video_path, stamps)
        review_summary = {
            "reviewed": True,
            "frames": len(frameset.frames),
            "contact_sheet": str(frameset.contact_sheet),
            "luma": dict(zip([round(s, 2) for s in stamps], luma)),
        }
        write_json(review_summary, attempt.review / "summary.json")

    video_sha = (
        sha256_file(str(render_result.video_path)) if render_result.video_path else None
    )
    report = run_manifest.DeliveryReport(
        run_dir=str(paths.root),
        attempt=number,
        spec_sha256=digest,
        scene_hashes=_scene_hashes(spec),
        renderer=adapter.name,
        renderer_version=adapter.version,
        passed=result.passed,
        stages=result.to_dict()["stages"],
        video=str(render_result.video_path) if render_result.video_path else None,
        video_sha256=video_sha,
        planned_duration_s=plan.total_duration_s,
        rendered_duration_s=render_result.duration_s,
        reviews=[review_summary],
        runtime={"cache_key": tools.cache_key(tools.resolve_runtime())},
    )
    run_manifest.write_delivery_report(attempt, report)

    manifest.qa_passed = result.passed
    manifest.qa_stages = result.to_dict()["stages"]
    manifest.video = str(render_result.video_path)
    manifest.video_sha256 = video_sha
    run_manifest.write_manifest(attempt, manifest)

    _log("")
    _log(f"Delivery report: {attempt.artifact / 'delivery-report.json'}")
    _log(f"Verdict: {'PASS' if result.passed else 'FAIL'}")
    return 0 if result.passed else 1


def cmd_design(args: argparse.Namespace) -> int:
    """Run the design-harness loop on a spec and write the repaired result.

    Mechanically fixes the spec-level blockers it can (today: non-positive
    scene durations) and leaves taste-level blockers to a repair agent. With no
    agent wired it repairs what it can and otherwise stops in the blocked state,
    so the command never silently ships a broken spec.

    Without ``--render`` the loop verifies only the spec-level gates (pure
    Python, no encoder). With ``--render`` it also drives the renderer -- emit
    the project, render the MP4, and run the full gate set on the artifact --
    feeding those findings back into the same repair router. If the renderer
    cannot run in this environment the loop degrades to spec-level and records
    the reason in the session's ``render_attestation``; it never silently ships.
    """
    spec = load_spec(args.spec)
    settings = harness_designer.DesignerSettings(
        max_turns=args.max_turns,
        default_scene_duration_s=args.default_duration_s,
    )
    driver = None
    if args.render:
        driver = harness_orchestrator.make_runtime_driver(
            renderer=args.renderer, workspace=args.workspace
        )
    session = harness_designer.run_design_loop(
        spec,
        settings=settings,
        driver=driver,
        workspace=args.workspace,
    )
    _log(str(session))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        from .spec.io import save

        save(session.final_spec, out / "spec.designed.json")
        write_json(session.to_dict(), out / "design-session.json")
        _log(f"  wrote {out / 'spec.designed.json'}")
        _log(f"  wrote {out / 'design-session.json'}")
    return 0 if session.shippable else 1


def cmd_bench(args: argparse.Namespace) -> int:
    """Compare how well different harnesses spot a bad artifact.

    Two rows are always cheap: ``colophon`` (our own gates) and ``naive`` (the
    "it rendered, ship it" baseline an unchecked agent would use). The external
    rows are real and really wired, but they stay off unless you pass
    ``--agents``, because running a coding agent spends money, needs network and
    credentials, takes minutes, and cannot be reproduced byte-for-byte.

    Run without ``--agents`` to see whether our instrument works. Run with it
    when you actually want to compare against another agent.
    """
    spec = None
    if args.spec:
        spec = load_spec(Path(args.spec))

    report = harness_matrix.run_matrix_demo(
        spec,
        agents=args.agents,
        timeout_s=args.timeout,
        workdir=Path(args.workspace) if args.workspace else None,
    )

    if args.json:
        # Flattened first: the in-memory cells are keyed by (brief, harness)
        # tuples, which JSON has no way to express.
        _log(json.dumps(harness_matrix.json_safe(report), indent=2, default=str))
        return 0

    _log(format_matrix(report))
    _log("")
    cells = report["cells"]
    colophon_good = cells[("good_artifact", "colophon")]["passed"]
    colophon_broken = not cells[("broken_stutter", "colophon")]["passed"]
    naive_broken = cells[("broken_stutter", "naive")]["passed"]
    _log(
        "thesis: colophon accepts the good artifact"
        f" ({colophon_good}) and rejects the stutter ({colophon_broken});"
        f" naive accepts the stutter ({naive_broken})."
    )
    if not args.agents:
        _log("")
        _log(
            "external agents were not run. Add --agents to actually invoke"
            " codex/claude (costs money, needs network, not reproducible)."
        )
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Expose colophon as MCP tools over HTTP.

    This is the seam an agent harness plugs into. Colophon supplies the gates
    (ground truth); the harness supplies the loop, the tools and the session
    state. ``colophon mcp serve`` is all that is needed — everything else is
    ordinary tool calls the harness discovers for itself.
    """
    from .mcp_server import main as mcp_main

    cmd = ["serve", "--host", args.host, "--port", str(args.port)]
    if args.root:
        cmd += ["--root", args.root]
    if args.token:
        cmd += ["--token", args.token]
    return mcp_main(cmd)


def cmd_resume(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    number = run_manifest.resumable_attempt(paths)
    if number is None:
        _log("No resumable attempt found.")
        return 0
    attempt = run_layout.begin_attempt(paths, number)
    report = run_manifest.read_delivery_report(attempt)
    _log(f"Resumable attempt: {number:02d}")
    if report:
        _log(f"  passed: {report.get('passed')}")
        _log(f"  video:  {report.get('video')}")
        _log(f"  spec:   {report.get('spec_sha256')}")
    return 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colophon",
        description="Spec-first video generation with machine-checkable taste.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("doctor", help="check the runtime")
    p.add_argument("--run-dir")
    p.set_defaults(func=cmd_doctor)

    p = commands.add_parser("init", help="freeze a spec into a new run")
    p.add_argument("spec")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_init)

    p = commands.add_parser("plan", help="lay scenes onto the clock")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_plan)

    p = commands.add_parser("validate", help="validate spec and timeline")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_validate)

    p = commands.add_parser("emit", help="spec -> editable project")
    p.add_argument("run_dir")
    p.add_argument("--renderer", default=DEFAULT_RENDERER)
    p.add_argument("--attempt", type=int)
    p.set_defaults(func=cmd_emit)

    p = commands.add_parser("render", help="project -> MP4")
    p.add_argument("run_dir")
    p.add_argument("--renderer", default=DEFAULT_RENDERER)
    p.add_argument("--attempt", type=int)
    p.set_defaults(func=cmd_render)

    p = commands.add_parser("qa", help="run deterministic QA")
    p.add_argument("run_dir")
    p.add_argument("--attempt", type=int)
    p.set_defaults(func=cmd_qa)

    p = commands.add_parser("review", help="extract frames for visual review")
    p.add_argument("run_dir")
    p.add_argument("--attempt", type=int)
    p.set_defaults(func=cmd_review)

    p = commands.add_parser(
        "record-review", help="validate an independent review and merge the verdicts"
    )
    p.add_argument("run_dir")
    p.add_argument("--attempt", type=int)
    p.add_argument("--review", required=True, help="path to the review JSON")
    p.set_defaults(func=cmd_record_review)

    p = commands.add_parser("repair", help="apply targeted spec repairs")
    p.add_argument("run_dir")
    p.add_argument("ops", help="JSON file: [{scene_id, field, value}]")
    p.add_argument("--claim-edits", help="JSON file: {claim_id: new text}")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_repair)

    p = commands.add_parser("deliver", help="run the full pipeline")
    p.add_argument("run_dir")
    p.add_argument("--renderer", default=DEFAULT_RENDERER)
    p.add_argument("--attempt", type=int)
    p.add_argument("--review", action="store_true", help="also build the review package")
    p.add_argument("--no-review", dest="review", action="store_false")
    p.set_defaults(func=cmd_deliver, review=True)

    p = commands.add_parser(
        "design", help="run the repair loop on a spec (mechanical fixes only)"
    )
    p.add_argument("spec", help="path to the spec JSON")
    p.add_argument("--out", help="directory to write the repaired spec + session")
    p.add_argument("--max-turns", type=int, default=harness_designer.MAX_DESIGNER_TURNS)
    p.add_argument(
        "--default-duration-s",
        type=float,
        default=harness_designer.DEFAULT_SCENE_DURATION_S,
    )
    p.add_argument(
        "--render",
        action="store_true",
        help="also drive the renderer (emit + render + full QA) each turn",
    )
    p.add_argument(
        "--renderer",
        default=DEFAULT_RENDERER,
        help="renderer adapter to use with --render (default: hyperframes)",
    )
    p.add_argument(
        "--workspace",
        help="directory for render attempts when --render is used",
    )
    p.set_defaults(func=cmd_design)

    p = commands.add_parser("resume", help="show the resumable attempt")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_resume)

    p = commands.add_parser(
        "bench", help="compare harnesses on known-good and known-bad artifacts"
    )
    p.add_argument(
        "--spec", help="optional spec, used as context when prompting live agents"
    )
    p.add_argument(
        "--agents",
        action="store_true",
        help="really run codex/claude (costs money, needs network, not reproducible)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=harness_matrix.DEFAULT_AGENT_TIMEOUT_S,
        help=f"per-agent timeout in seconds (default: {harness_matrix.DEFAULT_AGENT_TIMEOUT_S})",
    )
    p.add_argument(
        "--workspace",
        help="directory for live agent scratch work (default: a temp dir per run)",
    )
    p.add_argument("--json", action="store_true", help="emit the raw matrix as JSON")
    p.set_defaults(func=cmd_bench)

    p = commands.add_parser(
        "mcp", help="expose colophon as MCP tools over HTTP (for an agent harness)"
    )
    sub = p.add_subparsers(dest="mcp_command", required=True)
    s = sub.add_parser("serve", help="run the HTTP MCP server")
    s.add_argument(
        "--host", default=mcp_server.DEFAULT_HOST, help="interface to bind"
    )
    s.add_argument(
        "--port", type=int, default=mcp_server.DEFAULT_PORT, help="port to listen on"
    )
    s.add_argument(
        "--root",
        default=None,
        help=f"directory every tool path is confined to (defaults to ${mcp_server.sandbox.ROOT_ENV})",
    )
    s.add_argument(
        "--token",
        default=None,
        help=f"bearer token clients must present; required to bind beyond loopback (defaults to ${mcp_server.TOKEN_ENV})",
    )
    p.set_defaults(func=cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        return _fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
