"""Sound study of reference reels the owner sent. Layout under DIR: refaudio/<id>.wav, scribe/<id>.json (tools/stt.py), refvideo/<id>.cuts (ffmpeg scene times). Writes DIR/refsummary/<id>.md.

Join each reference's Scribe transcript, its audio and its cut times into one short sound-and-speech summary."""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

S = Path(sys.argv[1])
OUT = S / "refsummary"
OUT.mkdir(exist_ok=True)


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    line = [l for l in r.splitlines() if l.strip().startswith("I:")]
    return line[-1].split()[1] if line else "?"


for js in sorted((S / "scribe").glob("*.json")):
    rid = js.stem
    d = json.loads(js.read_text(encoding="utf-8"))
    words = [w for w in d["words"] if w["type"] == "word"]
    events = [(round(w["start"], 1), w["text"]) for w in d["words"] if w["type"] == "audio_event"]
    x = pcm(S / "refaudio" / f"{rid}.wav")
    dur = len(x) / 16000
    speech = np.zeros(len(x), bool)
    for w in words:
        speech[int(w["start"] * 16000):int(w["end"] * 16000) + 1600] = True
    rms = lambda a: float(np.sqrt(np.mean(a ** 2))) if len(a) else 0.0
    under = 20 * np.log10((rms(x[~speech]) + 1e-6) / (rms(x[speech]) + 1e-6))
    pauses = [round(b["start"] - a["end"], 2) for a, b in zip(words, words[1:]) if b["start"] - a["end"] > 0.4]
    spoken = sum(w["end"] - w["start"] for w in words)
    # Sentences with their start time, from punctuation in the transcript.
    sents, cur, t0 = [], [], None
    for w in words:
        t0 = w["start"] if t0 is None else t0
        cur.append(w["text"])
        if re.search(r"[.!?]$", w["text"]):
            sents.append((round(t0, 1), " ".join(cur)))
            cur, t0 = [], None
    if cur:
        sents.append((round(t0, 1), " ".join(cur)))
    cuts_file = S / "refvideo" / f"{rid}.cuts"
    cuts = [float(c) for c in cuts_file.read_text().split()] if cuts_file.exists() else []
    starts = np.array([w["start"] for w in words])
    on_word = sum(1 for c in cuts if len(starts) and np.min(np.abs(starts - c)) < 0.12)
    sent_starts = np.array([s for s, _ in sents])
    on_sent = sum(1 for c in cuts if len(sent_starts) and np.min(np.abs(sent_starts - c)) < 0.3)
    lines = [f"# {rid} sound and speech", "",
             f"- Duration {dur:.1f} s, loudness {lufs(S / 'refaudio' / f'{rid}.wav')} LUFS, language {d.get('language_code')}",
             f"- {len(words)} words, {len(words) / max(spoken, 0.1) * 60:.0f} words per spoken minute, speech fills {spoken / dur:.0%} of the video",
             f"- First word at {words[0]['start']:.2f} s" if words else "- No speech",
             f"- Pauses over 0.4 s: {pauses}",
             f"- Sound between words vs speech: {under:.1f} dB (above about -20 dB means music or effects carry the gaps)",
             f"- Audio events: {events or 'none tagged'}",
             (f"- Cuts: {len(cuts)} ({len(cuts) / dur:.2f} per second); {on_word} land within 0.12 s of a word start, "
              f"{on_sent} within 0.3 s of a sentence start" if cuts else "- Cuts: not measured"),
             "", "## Transcript (Scribe, may contain recognition errors)"]
    lines += [f"- {s:5.1f} s  {t}" for s, t in sents]
    (OUT / f"{rid}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("ok", rid)
