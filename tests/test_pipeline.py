import tempfile
import unittest
from pathlib import Path

from orchestrator import pipeline as p


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        p.start("v", self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def pass_stage(self, name):
        stage = p.BY_NAME[name]
        for reviewer in stage.reviewers:
            p.score("v", name, reviewer, 9, state_dir=self.dir)
        p.audit("v", name, "confirmed", state_dir=self.dir)
        if stage.owner_approval:
            p.approve("v", name, state_dir=self.dir)

    def row(self, name):
        return next(r for r in p.status("v", self.dir) if r["stage"] == name)

    def test_low_score_does_not_pass(self):
        p.score("v", "research", "fact-checker", 8, state_dir=self.dir)
        with self.assertRaises(p.GateError):
            p.audit("v", "research", "confirmed", state_dir=self.dir)
        self.assertFalse(self.row("research")["passed"])

    def test_open_issue_blocks_a_high_score(self):
        p.score("v", "research", "fact-checker", 10, issues=1, state_dir=self.dir)
        with self.assertRaises(p.GateError):
            p.audit("v", "research", "confirmed", state_dir=self.dir)

    def test_stage_needs_audit(self):
        p.score("v", "research", "fact-checker", 9, state_dir=self.dir)
        self.assertFalse(self.row("research")["passed"])
        p.audit("v", "research", "rejected", state_dir=self.dir)
        self.assertFalse(self.row("research")["passed"])

    def test_cannot_skip_a_stage(self):
        with self.assertRaises(p.GateError):
            p.score("v", "script", "script-reviewer", 10, state_dir=self.dir)

    def test_owner_must_approve_script_before_video_work(self):
        self.pass_stage("research")
        self.pass_stage("selection")
        for reviewer in p.BY_NAME["script"].reviewers:
            p.score("v", "script", reviewer, 10, state_dir=self.dir)
        p.audit("v", "script", "confirmed", state_dir=self.dir)
        with self.assertRaises(p.GateError):
            p.score("v", "style", "design-reviewer", 10, state_dir=self.dir)
        p.approve("v", "script", state_dir=self.dir)
        p.score("v", "style", "design-reviewer", 10, state_dir=self.dir)

    def test_owner_cannot_be_shown_unreviewed_work(self):
        with self.assertRaises(p.GateError):
            p.approve("v", "script", state_dir=self.dir)

    def test_new_score_voids_audit(self):
        self.pass_stage("research")
        p.score("v", "research", "fact-checker", 9, state_dir=self.dir)
        self.assertIsNone(self.row("research")["audit"])

    def test_new_round_clears_scores_and_is_capped(self):
        p.score("v", "research", "fact-checker", 9, state_dir=self.dir)
        p.new_round("v", "research", self.dir)
        self.assertEqual(self.row("research")["missing"], ["fact-checker"])
        for _ in range(p.MAX_ROUNDS - 2):
            p.new_round("v", "research", self.dir)
        with self.assertRaises(p.GateError):
            p.new_round("v", "research", self.dir)

    def test_unknown_reviewer_is_rejected(self):
        with self.assertRaises(p.GateError):
            p.score("v", "research", "script-reviewer", 10, state_dir=self.dir)

    def test_round_rejects_unknown_stage(self):
        with self.assertRaises(p.GateError):
            p.new_round("v", "nope", self.dir)

    def test_audit_rejects_unknown_stage(self):
        with self.assertRaises(p.GateError):
            p.audit("v", "nope", "rejected", state_dir=self.dir)

    def test_approve_rejects_unknown_stage(self):
        with self.assertRaises(p.GateError):
            p.approve("v", "nope", state_dir=self.dir)

    def test_score_outside_range_is_rejected(self):
        for value in (-1, 11):
            with self.assertRaises(p.GateError):
                p.score("v", "research", "fact-checker", value, state_dir=self.dir)

    def test_start_twice_and_unknown_slug_are_rejected(self):
        with self.assertRaises(p.GateError):
            p.start("v", self.dir)
        with self.assertRaises(p.GateError):
            p.status("other", self.dir)

    def test_new_round_keeps_history(self):
        p.score("v", "research", "fact-checker", 7, state_dir=self.dir)
        data = p.new_round("v", "research", self.dir)
        record = data["stages"]["research"]
        self.assertEqual(record["round"], 2)
        self.assertEqual(record["history"][0]["scores"]["fact-checker"]["score"], 7)


    def test_waived_stage_lets_the_next_one_score(self):
        p.waive("v", "research", "owner wrote it", self.dir)
        p.waive("v", "selection", "owner wrote it", self.dir)
        p.score("v", "script", "script-reviewer", 6, state_dir=self.dir)
        self.assertTrue(self.row("research")["waived"])

    def test_owner_approved_stage_cannot_be_waived(self):
        for name in ("script", "edit"):
            with self.assertRaises(p.GateError):
                p.waive("v", name, "no", self.dir)

    def test_waiver_needs_a_reason(self):
        with self.assertRaises(p.GateError):
            p.waive("v", "research", "", self.dir)


if __name__ == "__main__":
    unittest.main()
