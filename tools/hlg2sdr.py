"""Convert iPhone HDR video (HLG, BT.2020) to SDR BT.709 the way a phone shows it, so colours stay natural.

Plain decoding shows the HLG signal as if it were SDR: whites wash out and colours fade.
This undoes HLG with its system gamma, scales the result, softly rolls off highlights, converts
BT.2020 to BT.709 primaries and encodes with gamma 2.4. SCALE and GAMMA were fitted on 2026-11-03
to the owner's own Mac playback of `me/1.MOV` (brightness percentiles within about 0.01).

Usage: python tools/hlg2sdr.py in.MOV out.mkv [--start S] [--seconds S] [--fps 30]
       python tools/hlg2sdr.py in.MOV frame.png --frame-at S
The video output is lossless FFV1, for editing.
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

A, B, C = 0.17883277, 0.28466892, 0.55991073
M2020_709 = np.array([[1.6605, -0.5876, -0.0728],
                      [-0.1246, 1.1329, -0.0083],
                      [-0.0182, -0.1006, 1.1187]], np.float32)
SCALE = 1.2  # display-relative level that becomes SDR white; fitted, see above
KNEE = 0.75
GAMMA = 2.4


def hlg_to_sdr(sig: np.ndarray) -> np.ndarray:
    """sig: HLG R'G'B' in 0..1 (BT.2020). Returns BT.709 R'G'B' in 0..1."""
    e = np.where(sig <= 0.5, sig * sig / 3, (np.exp((sig - C) / A) + B) / 12)
    ys = e @ np.array([0.2627, 0.6780, 0.0593], np.float32)
    disp = e * np.power(np.maximum(ys, 1e-6), 0.2)[..., None]  # HLG system gamma 1.2 at 1000 nits
    lin = (disp / SCALE) @ M2020_709.T
    lin = np.maximum(lin, 0)
    over = lin > KNEE  # roll off highlights instead of clipping them
    lin = np.where(over, KNEE + (1 - KNEE) * (1 - np.exp(-(lin - KNEE) / (1 - KNEE))), lin)
    return np.power(np.clip(lin, 0, 1), 1 / GAMMA)


def probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                          "-show_entries", "stream_side_data=rotation", "-of", "default=nw=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    vals = dict(l.split("=", 1) for l in out.split() if "=" in l)
    w, h = int(vals["width"]), int(vals["height"])
    return (h, w) if vals.get("rotation", "0").lstrip("-") in ("90", "270") else (w, h)


def decode(path: Path, start: float, seconds: float | None, fps: float | None):
    w, h = probe_size(path)
    vf = ("scale=in_color_matrix=bt2020:in_range=tv:out_range=pc" + (f",fps={fps}" if fps else "")
          + ",format=rgb48le")
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path)]
    if seconds:
        cmd += ["-t", str(seconds)]
    proc = subprocess.Popen(cmd + ["-vf", vf, "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = w * h * 3 * 2
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, "<u2").reshape(h, w, 3).astype(np.float32) / 65535, (w, h)
    proc.stdout.close()
    proc.kill()
    proc.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--frame-at", type=float, help="Write one PNG frame at this time instead of a video")
    args = ap.parse_args()
    if args.frame_at is not None:
        frames = decode(args.src, args.frame_at, 0.1, None)
        sig, _ = next(frames)
        frames.close()
        Image.fromarray((hlg_to_sdr(sig) * 255 + 0.5).astype(np.uint8)).save(args.out)
        print("ok", args.out)
        return
    enc = None
    for n, (sig, (w, h)) in enumerate(decode(args.src, args.start, args.seconds, args.fps)):
        if enc is None:
            enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                                    "-r", str(args.fps), "-i", "-", "-c:v", "ffv1", "-pix_fmt", "rgb24",
                                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "rgb",
                                    str(args.out)], stdin=subprocess.PIPE)
        enc.stdin.write((hlg_to_sdr(sig) * 255 + 0.5).astype(np.uint8).tobytes())
        if n % 30 == 0:
            print("frame", n, flush=True)
    enc.stdin.close()
    enc.wait()
    print("ok", args.out)


if __name__ == "__main__":
    main()
