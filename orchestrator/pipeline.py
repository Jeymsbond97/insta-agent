"""Quality gates for the production pipeline.

Each stage needs a passing score from every required reviewer and a confirmed audit.
Some stages also need owner approval. A stage cannot advance until the earlier one passed.
"""
import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state" / "pipeline"
PASS_SCORE = 9
MAX_ROUNDS = 2


@dataclass(frozen=True)
class Stage:
    name: str
    reviewers: tuple[str, ...]
    owner_approval: bool = False


# Owner's rule 2026-11-02: makers get the reviewers' criteria and check their own work, so only three
# stages are gated, each with few reviewers and at most two rounds.
STAGES = (
    Stage("research", ("fact-checker",)),
    Stage("script", ("script-reviewer", "uzbek-language-reviewer", "fact-checker"), owner_approval=True),
    Stage("edit", ("design-reviewer", "edit-reviewer", "uzbek-language-reviewer"), owner_approval=True),
)
BY_NAME = {s.name: s for s in STAGES}


class GateError(Exception):
    pass


def require_stage(stage_name: str):
    if stage_name not in BY_NAME:
        raise GateError(f"Unknown stage: {stage_name}")


def _path(slug: str, state_dir: Path) -> Path:
    return state_dir / f"{slug}.json"


def load(slug: str, state_dir: Path = STATE_DIR) -> dict:
    path = _path(slug, state_dir)
    if not path.exists():
        raise GateError(f"Not started: {slug}")
    return json.loads(path.read_text(encoding="utf-8"))


def save(data: dict, state_dir: Path = STATE_DIR):
    state_dir.mkdir(parents=True, exist_ok=True)
    _path(data["slug"], state_dir).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def start(slug: str, state_dir: Path = STATE_DIR) -> dict:
    if _path(slug, state_dir).exists():
        raise GateError(f"Already started: {slug}")
    data = {"slug": slug, "created": time.time(), "stages": {
        s.name: {"round": 1, "scores": {}, "audit": None, "owner": False, "history": []} for s in STAGES}}
    save(data, state_dir)
    return data


def passed_reviews(stage: Stage, record: dict) -> bool:
    return all(r in record["scores"] and record["scores"][r]["score"] >= PASS_SCORE
               and record["scores"][r]["issues"] == 0 for r in stage.reviewers)


def stage_passed(stage: Stage, record: dict) -> bool:
    if record.get("waived"):
        return True
    if not passed_reviews(stage, record) or record["audit"] != "confirmed":
        return False
    return record["owner"] or not stage.owner_approval


def require_previous(data: dict, stage_name: str):
    for stage in STAGES:
        if stage.name == stage_name:
            return
        if not stage_passed(stage, data["stages"][stage.name]):
            raise GateError(f"Stage '{stage.name}' has not passed yet")


def score(slug: str, stage_name: str, reviewer: str, value: int, issues: int = 0, artifact: str = "",
          state_dir: Path = STATE_DIR) -> dict:
    require_stage(stage_name)
    if reviewer not in BY_NAME[stage_name].reviewers:
        raise GateError(f"{reviewer} is not a reviewer of {stage_name}")
    if not 0 <= value <= 10:
        raise GateError("Score must be 0-10")
    data = load(slug, state_dir)
    require_previous(data, stage_name)
    record = data["stages"][stage_name]
    record["scores"][reviewer] = {"score": value, "issues": issues, "artifact": artifact, "ts": time.time()}
    record["audit"] = None
    record["owner"] = False
    save(data, state_dir)
    return data


def new_round(slug: str, stage_name: str, state_dir: Path = STATE_DIR) -> dict:
    """The artifact changed, so all its scores are void."""
    require_stage(stage_name)
    data = load(slug, state_dir)
    record = data["stages"][stage_name]
    if record["round"] >= MAX_ROUNDS:
        raise GateError(f"{MAX_ROUNDS} rounds used. Report to the owner instead of retrying.")
    record["history"].append({"round": record["round"], "scores": record["scores"], "audit": record["audit"]})
    record.update(round=record["round"] + 1, scores={}, audit=None, owner=False)
    save(data, state_dir)
    return data


def audit(slug: str, stage_name: str, verdict: str, note: str = "", state_dir: Path = STATE_DIR) -> dict:
    if verdict not in ("confirmed", "rejected"):
        raise GateError("Verdict must be confirmed or rejected")
    require_stage(stage_name)
    data = load(slug, state_dir)
    record = data["stages"][stage_name]
    if verdict == "confirmed" and not passed_reviews(BY_NAME[stage_name], record):
        raise GateError("Cannot confirm: reviewers have not all passed")
    record["audit"] = verdict
    record["audit_note"] = note
    save(data, state_dir)
    return data


def approve(slug: str, stage_name: str, state_dir: Path = STATE_DIR) -> dict:
    require_stage(stage_name)
    data = load(slug, state_dir)
    stage, record = BY_NAME[stage_name], data["stages"][stage_name]
    if not stage.owner_approval:
        raise GateError(f"{stage_name} does not use owner approval")
    if not passed_reviews(stage, record) or record["audit"] != "confirmed":
        raise GateError("Reviews and audit must pass before the owner sees this")
    record["owner"] = True
    save(data, state_dir)
    return data


def waive(slug: str, stage_name: str, note: str, state_dir: Path = STATE_DIR) -> dict:
    """The owner said this stage does not apply. Stages the owner approves cannot be waived."""
    require_stage(stage_name)
    if BY_NAME[stage_name].owner_approval:
        raise GateError(f"{stage_name} needs owner approval and cannot be waived")
    if not note:
        raise GateError("A waiver needs the owner's reason")
    data = load(slug, state_dir)
    data["stages"][stage_name].update(waived=True, waiver_note=note)
    save(data, state_dir)
    return data


def status(slug: str, state_dir: Path = STATE_DIR) -> list[dict]:
    data = load(slug, state_dir)
    rows = []
    for stage in STAGES:
        record = data["stages"][stage.name]
        rows.append({"stage": stage.name, "round": record["round"], "passed": stage_passed(stage, record),
                     "missing": [r for r in stage.reviewers if r not in record["scores"]],
                     "low": {r: v["score"] for r, v in record["scores"].items()
                             if v["score"] < PASS_SCORE or v["issues"]},
                     "audit": record["audit"], "owner": record["owner"] if stage.owner_approval else None,
                     "waived": record.get("waived", False)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start").add_argument("slug")
    sub.add_parser("status").add_argument("slug")
    s = sub.add_parser("score")
    for name in ("slug", "stage", "reviewer"):
        s.add_argument(name)
    s.add_argument("value", type=int)
    s.add_argument("--issues", type=int, default=0)
    s.add_argument("--artifact", default="")
    r = sub.add_parser("round")
    r.add_argument("slug")
    r.add_argument("stage")
    a = sub.add_parser("audit")
    a.add_argument("slug")
    a.add_argument("stage")
    a.add_argument("verdict")
    a.add_argument("--note", default="")
    o = sub.add_parser("approve")
    o.add_argument("slug")
    o.add_argument("stage")
    w = sub.add_parser("waive")
    w.add_argument("slug")
    w.add_argument("stage")
    w.add_argument("--note", default="")
    args = ap.parse_args()
    try:
        if args.cmd == "start":
            start(args.slug)
        elif args.cmd == "score":
            score(args.slug, args.stage, args.reviewer, args.value, args.issues, args.artifact)
        elif args.cmd == "round":
            new_round(args.slug, args.stage)
        elif args.cmd == "audit":
            audit(args.slug, args.stage, args.verdict, args.note)
        elif args.cmd == "approve":
            approve(args.slug, args.stage)
        elif args.cmd == "waive":
            waive(args.slug, args.stage, args.note)
        for row in status(args.slug):
            print(json.dumps(row, ensure_ascii=False))
    except GateError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
