import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_independent_review_packet_contains_only_pending_entries():
    packet_path = ROOT / "outputs" / "independent-review-packet.json"
    assert packet_path.exists(), "run the packet builder before publishing the reviewer packet"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert len(packet) == 33
    assert {entry["first_pass_status"] for entry in packet} == {"CONFIRMED", "REJECTED"}
    assert all(entry["reviewer"] == "" for entry in packet)
    assert all(entry["decision"] == "" for entry in packet)
    assert all(entry["note"] == "" for entry in packet)
    assert all(entry["source_sha256"] and entry["quote"] for entry in packet)
