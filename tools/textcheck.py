"""Mechanical checks on Uzbek text before any reviewer reads it.

Finds wrong apostrophe characters, dashes to justify, spacing errors and length.
Exit code 1 when something must be fixed. Usage: python tools/textcheck.py script.md [more files]
"""
import re
import sys
from pathlib import Path

WPM = 170  # the owner's brisk delivery: TTS speed 1.2 plus atempo 1.12
MAX_SECONDS = 59
OKINA = "ʻ"  # oʻ gʻ
GLOTTAL = "ʼ"  # maʼno
WRONG_MARKS = "'`‘’´"


def check(text: str) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    for n, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(rf"([oOgG])[{re.escape(WRONG_MARKS)}{GLOTTAL}]", line):
            errors.append(f"line {n}: '{m.group(0)}' should use U+02BB: {m.group(1)}{OKINA}")
        for m in re.finditer(rf"(?<=\w)[{re.escape(WRONG_MARKS)}](?=\w)", line):
            if line[m.start() - 1] not in "oOgG":
                errors.append(f"line {n}: apostrophe in '{line[max(0, m.start() - 6):m.end() + 6]}' should be U+02BC")
        if "  " in line:
            errors.append(f"line {n}: double space")
        if re.search(r"\s[,.!?;:]", line):
            errors.append(f"line {n}: space before punctuation")
        for m in re.finditer(r"[—–]", line):
            notes.append(f"line {n}: dash in '{line[max(0, m.start() - 15):m.end() + 15]}', keep only where grammar requires")
    words = len(re.findall(r"\w+", re.sub(r"\[[^\]]*\]", "", text)))  # voice tags are not spoken
    seconds = words / WPM * 60
    notes.append(f"{words} words, about {seconds:.0f} s at {WPM} words per minute")
    if seconds > MAX_SECONDS:
        errors.append(f"too long: about {seconds:.0f} s, limit {MAX_SECONDS} s")
    return errors, notes


def main():
    failed = False
    for name in sys.argv[1:]:
        errors, notes = check(Path(name).read_text(encoding="utf-8"))
        print(f"== {name}")
        for e in errors:
            print("ERROR", e)
        for n in notes:
            print("note ", n)
        failed |= bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
