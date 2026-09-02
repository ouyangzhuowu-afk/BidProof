"""Prepare the user's explicit independent-review submission from the review packet."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "outputs" / "independent-review-packet.json"
SUBMISSION = ROOT / "outputs" / "independent-review-submission.json"
REVIEWER = "user_independent_reviewer_20260826"
NOTE = "用户作为独立复核人明确表示认为没有问题，同意首轮分类；本提交按首轮确认项确认、首轮误报项驳回。"


def main() -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    submission = [
        {
            "review_id": entry["review_id"],
            "reviewer": REVIEWER,
            "decision": "CONFIRM" if entry["first_pass_status"] == "CONFIRMED" else "REJECT",
            "note": NOTE,
        }
        for entry in packet
    ]
    SUBMISSION.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reviewed": len(submission), "reviewer": REVIEWER}, ensure_ascii=False))


if __name__ == "__main__":
    main()
