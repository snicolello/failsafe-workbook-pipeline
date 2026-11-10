"""Capture four generated HTML boards with Chromium and combine them with Pillow.

    python demo/build_clip.py --browser /path/to/chrome --runs build/demo

This optional maintainer utility does not run during the workbook demo.
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def build_clip(browser, runs, output, preview):
    boards = [(runs / f"run{n}" / "board.html").resolve(strict=True) for n in range(1, 5)]
    frames = []
    with tempfile.TemporaryDirectory(prefix="workbook-board-") as directory:
        temp = Path(directory)
        for index, board in enumerate(boards, start=1):
            screenshot = temp / f"run-{index}.png"
            subprocess.run([
                str(browser), "--headless", "--disable-gpu", "--hide-scrollbars",
                "--no-first-run", "--disable-extensions", "--disable-background-networking",
                "--force-device-scale-factor=1", "--window-size=1100,700",
                f"--user-data-dir={temp / 'browser'}", f"--screenshot={screenshot}",
                board.as_uri(),
            ], check=True, timeout=45, capture_output=True)
            with Image.open(screenshot) as capture:
                frames.append(capture.convert("RGB").quantize(colors=128))
            if index == 2:
                preview.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(screenshot, preview)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, save_all=True, append_images=frames[1:],
                   duration=4000, loop=0, optimize=False, disposal=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", required=True, type=Path)
    parser.add_argument("--runs", type=Path, default=Path("build/demo"))
    parser.add_argument("--output", type=Path, default=Path("demo/walkthrough.gif"))
    parser.add_argument("--preview", type=Path, default=Path("demo/status-board.png"))
    args = parser.parse_args()
    build_clip(args.browser, args.runs, args.output, args.preview)
