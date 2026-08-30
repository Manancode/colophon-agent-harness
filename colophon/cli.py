"""The ``colophon`` command line.

Pipeline:

    doctor    check the runtime
    init      freeze a spec into a new run
    plan      lay the scenes onto the clock
    validate  spec + timeline, no rendering
    emit      spec -> editable video project
    render    project -> MP4
    qa        run the deterministic stage pipeline
    review    extract frames + contact sheet for visual review
    repair    apply targeted spec ops
    deliver   everything above, end to end
    resume    continue from the last attempt that matches the frozen spec
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
from .qa.runner import format_report
from .qa.stages import grounding as grounding_stage
from .qa.stages import media as media_stage
from .qa.stages import spec as spec_stage
from .qa.stages import static as static_stage
from .qa.stages import taste as taste_stage
from .qa.stages import delivery as delivery_stage
from .qa.stages import motion_velocity as motion_velocity_stage
from .renderers.base import get_adapter
from .review import extract as review_extract
from .runs import layout as run_layout
from .runs import manifest as run_manifest
from .runtime import tools
from .spec.hash import sha256_file, spec_sha256
from .spec.io import load as load_spec
from .spec.io import write_json
from .spec.schema import VideoSpec
from .timeline.plan import build_plan

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
    paths = run_layout.init_run(args.run_dir, spec)
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
    number = args.attempt or run_layout.latest_attempt(paths)
    if number is None:
        return _fail("no attempts to check")
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
        },
        spec_sha256=spec_sha256(spec),
    )
    print(format_report(result))
    fp = eval_protocol.compute_eval_fingerprint()
    print(eval_protocol.format_eval_fingerprint(fp))
    write_json({"eval_fingerprint": fp, **result.to_dict()}, attempt.qa / "qa-report.json")
    return 0 if result.passed else 1


def cmd_review(args: argparse.Namespace) -> int:
    paths = run_layout.run_paths(args.run_dir)
    spec = load_spec(paths.spec)
    spec, plan, _ = _plan_for(spec)
    number = args.attempt or run_layout.latest_attempt(paths)
    if number is None:
        return _fail("no attempts to review")
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

    _log(f"Extracted {len(frameset.frames)} frames to {frames}")
    _log(f"Contact sheet: {sheet}")
    _log("")
    _log("Frame luma (a bare canvas reads ~25; higher means content):")
    for t, value in zip(frameset.timestamps, review_extract.luminance_at(video, stamps)):
        shown = f"{value:.2f}" if value is not None else "n/a"
        _log(f"  t={t:>6.2f}s  YAVG {shown}")
    return 0


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
            # Only cmd_deliver knows this: QA runs after the encode, so the
            # delivery gate can compare the measured artifact against the
            # timeline instead of guessing from the spec. cmd_qa has no
            # artifact and deliberately leaves it out.
            "rendered_duration_s": render_result.duration_s,
        },
        spec_sha256=digest,
    )
    print(format_report(result))
    fp = eval_protocol.compute_eval_fingerprint()
    print(eval_protocol.format_eval_fingerprint(fp))
    write_json({"eval_fingerprint": fp, **result.to_dict()}, attempt.qa / "qa-report.json")

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

    p = commands.add_parser("resume", help="show the resumable attempt")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_resume)

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
