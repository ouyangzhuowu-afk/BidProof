"""Create a reviewer-facing packet without changing the ground-truth ledger."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "outputs" / "ground-truth-review-ledger.json"
PACKET_JSON = ROOT / "outputs" / "independent-review-packet.json"
PACKET_MD = ROOT / "outputs" / "independent-review-packet.md"


def build_packet() -> list[dict]:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    return [
        {
            "review_id": entry["review_id"],
            "fixture_id": entry["fixture_id"],
            "source_path": entry["source_path"],
            "source_sha256": entry["source_sha256"],
            "page": entry["page"],
            "category": entry["category"],
            "severity": entry["severity"],
            "quote": entry["quote"],
            "first_pass_status": entry["first_pass_status"],
            "reviewer": "",
            "decision": "",
            "note": "",
        }
        for entry in ledger.get("entries", [])
        if entry.get("human_status") == "PENDING_INDEPENDENT_REVIEW"
    ]


def write_packet() -> dict[str, int]:
    packet = build_packet()
    PACKET_JSON.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 独立 Ground Truth 复核包",
        "",
        "本文件由 `work/build_independent_review_packet.py` 从当前台账生成。它是复核输入包，不是正式台账；填写后必须由项目流程显式应用。",
        "",
        f"- 待复核：{len(packet)} 条",
        "- 复核人：必须不同于 `codex_first_pass`",
        "- 决定：只能填写 `CONFIRM` 或 `REJECT`",
        "- 证据：重新打开 `source_path`，核对 SHA-256、页码和完整 quote",
        "- 注意：`CONFIRM` 只确认候选标签和引用成立，不代表企业满足要求",
        "",
        "## 提交文件",
        "",
        "请复制 `independent-review-packet.json`，为每条填写 `reviewer`、`decision` 和非空 `note`；不要直接修改 `ground-truth-review-ledger.json`。",
        "",
    ]
    for entry in packet:
        lines.extend(
            [
                f"### {entry['review_id']} · {entry['category']} · {entry['severity']}",
                f"- 文件：`{entry['source_path']}`",
                f"- 页码：第 {entry['page']} 页",
                f"- 首轮：`{entry['first_pass_status']}`",
                f"- Quote：{entry['quote']}",
                "- 独立决定：待填写",
                "",
            ]
        )
    PACKET_MD.write_text("\n".join(lines), encoding="utf-8")
    return {"entries": len(packet), "json_bytes": PACKET_JSON.stat().st_size, "markdown_bytes": PACKET_MD.stat().st_size}


if __name__ == "__main__":
    print(json.dumps(write_packet(), ensure_ascii=False))
