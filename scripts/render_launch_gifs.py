#!/usr/bin/env python3
"""Render small reviewed launch GIFs for the public README."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "assets" / "launch"
CANVAS_SIZE = (840, 472)
BACKGROUND = (13, 18, 26)
PANEL = (20, 27, 38)
TERMINAL = (8, 12, 18)
TEXT = (229, 236, 246)
MUTED = (139, 152, 170)
GREEN = (67, 196, 118)
RED = (238, 92, 92)
YELLOW = (240, 183, 86)
BLUE = (88, 166, 255)
Image = None
ImageDraw = None
ImageFont = None


@dataclass(frozen=True)
class Frame:
    """One reviewed terminal-style launch frame."""

    title: str
    subtitle: str
    command: str
    lines: tuple[str, ...]
    status: str
    accent: tuple[int, int, int]


@dataclass(frozen=True)
class Animation:
    """A deterministic launch animation."""

    filename: str
    frames: tuple[Frame, ...]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for checkout-demo.gif and ai-regression-proof.gif.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for animation in _animations():
        path = output_dir / animation.filename
        _render_animation(animation, path)
        print(f"wrote {path.relative_to(REPO_ROOT)} ({path.stat().st_size} bytes)")

    return 0


def _animations() -> tuple[Animation, ...]:
    return (
        Animation(
            filename="checkout-demo.gif",
            frames=(
                Frame(
                    title="Checkout demo",
                    subtitle="A clean two-minute local proof",
                    command="$ scripts/demo.sh",
                    lines=(
                        "Starting checkout fixture API on localhost",
                        "Loading qanstitution.yaml",
                        "Discovered 4 Hurl tests",
                        "Injecting gates into temporary execution copies",
                    ),
                    status="demo proof is running",
                    accent=BLUE,
                ),
                Frame(
                    title="QAnstitution gates",
                    subtitle="Policy is injected without changing source tests",
                    command="$ entroping run --ci --report json --report junit --report html",
                    lines=(
                        "status_success -> status < 500",
                        "checkout_latency -> duration < 750ms",
                        "request_id_header -> header X-Request-Id exists",
                        "source .hurl files remain unchanged",
                    ),
                    status="policy compiled for Hurl",
                    accent=YELLOW,
                ),
                Frame(
                    title="Hurl decides",
                    subtitle="The CI boundary stays deterministic and LLM-free",
                    command="$ hurl --test tests/generated/*.hurl",
                    lines=(
                        "checkout_smoke.hurl ........ PASS",
                        "checkout_create.hurl ....... PASS",
                        "checkout_update.hurl ....... PASS",
                        "checkout_summary.hurl ...... PASS",
                    ),
                    status="Hurl run: 4 passed, 0 failed",
                    accent=GREEN,
                ),
                Frame(
                    title="Reports are ready",
                    subtitle="Evidence for local review, CI, and pull requests",
                    command="$ ls reports",
                    lines=(
                        "run-latest.json",
                        "junit.xml",
                        "run-latest.html",
                        "latest-run state updated under .entroping/",
                    ),
                    status="checkout proof is reproducible",
                    accent=GREEN,
                ),
            ),
        ),
        Animation(
            filename="ai-regression-proof.gif",
            frames=(
                Frame(
                    title="AI regression proof",
                    subtitle="The response body looks fine, but behavior drifted",
                    command="$ scripts/ai_regression_demo.sh",
                    lines=(
                        "AI-generated handler returns HTTP 200",
                        "JSON body still matches the happy-path example",
                        "Required X-Request-Id header is missing",
                        "Static review would be easy to miss",
                    ),
                    status="runtime behavior is the source of truth",
                    accent=BLUE,
                ),
                Frame(
                    title="Policy catches it",
                    subtitle="A global QAnstitution gate applies to every run",
                    command="$ entroping run --tag checkout --report json",
                    lines=(
                        "status_success ............. PASS",
                        "body_shape .................. PASS",
                        "request_id_header .......... FAIL",
                        "gate: header X-Request-Id exists",
                    ),
                    status="QAnstitution blocked the regression",
                    accent=RED,
                ),
                Frame(
                    title="Failure evidence",
                    subtitle="The report is actionable without exposing secrets",
                    command="$ entroping report bug",
                    lines=(
                        "rule_id: request_id_header",
                        "file: tests/generated/checkout_smoke.hurl",
                        "redacted stdout and stderr captured",
                        "copyable bug template generated",
                    ),
                    status="bad PR gets a deterministic stop sign",
                    accent=RED,
                ),
                Frame(
                    title="Fix and rerun",
                    subtitle="The same gate proves the repair",
                    command="$ scripts/ai_regression_demo.sh --fixed",
                    lines=(
                        "handler restores X-Request-Id",
                        "temporary gate injection reruns through Hurl",
                        "reports refresh from the same command path",
                        "CI stays reproducible without model access",
                    ),
                    status="regression fixed: 4 passed, 0 failed",
                    accent=GREEN,
                ),
            ),
        ),
    )


def _render_animation(animation: Animation, path: Path) -> None:
    _load_pillow()
    frames = [
        _draw_frame(frame, index=index, total=len(animation.frames))
        for index, frame in enumerate(animation.frames, start=1)
    ]
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=1150,
        loop=0,
        optimize=True,
        disposal=2,
    )


def _draw_frame(frame: Frame, *, index: int, total: int) -> Image.Image:
    image = Image.new("RGB", CANVAS_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = _font(28, bold=True)
    subtitle_font = _font(16)
    body_font = _font(18)
    small_font = _font(14)
    mono_font = _mono_font(17)

    draw.rounded_rectangle((24, 22, 816, 450), radius=24, fill=PANEL)
    draw.rounded_rectangle((24, 22, 816, 450), radius=24, outline=(42, 54, 72), width=2)
    draw.rectangle((24, 22, 816, 30), fill=frame.accent)

    draw.text((52, 52), "ENTROPING", font=small_font, fill=frame.accent)
    draw.text((52, 78), frame.title, font=title_font, fill=TEXT)
    draw.text((52, 114), frame.subtitle, font=subtitle_font, fill=MUTED)

    draw.text((724, 60), f"{index}/{total}", font=small_font, fill=MUTED)
    progress_left = 704
    progress_top = 88
    progress_width = 70
    draw.rounded_rectangle(
        (progress_left, progress_top, progress_left + progress_width, progress_top + 8),
        radius=4,
        fill=(35, 45, 60),
    )
    draw.rounded_rectangle(
        (
            progress_left,
            progress_top,
            progress_left + int(progress_width * index / total),
            progress_top + 8,
        ),
        radius=4,
        fill=frame.accent,
    )

    terminal_box = (52, 152, 788, 382)
    draw.rounded_rectangle(terminal_box, radius=16, fill=TERMINAL, outline=(55, 67, 84), width=1)
    _draw_window_controls(draw)

    draw.text((84, 184), frame.command, font=mono_font, fill=TEXT)
    y = 222
    for line in frame.lines:
        color = _line_color(line)
        draw.text((84, y), line, font=mono_font, fill=color)
        y += 30

    status_box = (52, 396, 788, 426)
    draw.rounded_rectangle(status_box, radius=14, fill=(24, 34, 47), outline=frame.accent)
    draw.text((72, 402), frame.status, font=body_font, fill=frame.accent)
    return image


def _draw_window_controls(draw: ImageDraw.ImageDraw) -> None:
    colors = ((244, 94, 94), (245, 188, 86), (77, 190, 117))
    x = 74
    for color in colors:
        draw.ellipse((x, 170, x + 12, 182), fill=color)
        x += 22


def _line_color(line: str) -> tuple[int, int, int]:
    if "FAIL" in line or "blocked" in line:
        return RED
    if "PASS" in line or "passed" in line or "fixed" in line:
        return GREEN
    if "gate:" in line or "QAnstitution" in line:
        return YELLOW
    return TEXT


def _font(size: int, *, bold: bool = False):
    candidates = (
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _mono_font(size: int):
    candidates = (
        "Menlo.ttc",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_pillow() -> None:
    global Image, ImageDraw, ImageFont
    if Image is not None:
        return
    try:
        from PIL import Image as pillow_image
        from PIL import ImageDraw as pillow_image_draw
        from PIL import ImageFont as pillow_image_font
    except ImportError as exc:  # pragma: no cover - exercised by humans rebuilding assets.
        raise SystemExit(
            "Pillow is required to render launch GIFs. "
            "Run: uv run --with pillow python scripts/render_launch_gifs.py"
        ) from exc

    Image = pillow_image
    ImageDraw = pillow_image_draw
    ImageFont = pillow_image_font


if __name__ == "__main__":
    raise SystemExit(main())
