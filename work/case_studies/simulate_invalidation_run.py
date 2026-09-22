"""Run BidProof evidence matching on the public invalidation case."""

from pathlib import Path
import json
from app.extraction import extract_file
from app.rules import extract_requirements, match_evidence

tender_path = Path("work/fixtures/source2-nanjing.pdf")
evidence_path = Path("work/case_studies/enterprise_beta_disqualified.pdf")

tender_pages = extract_file(tender_path)
evidence_pages = extract_file(evidence_path)

for p in evidence_pages:
    p["source_filename"] = evidence_path.name
    p["source_id"] = "EVD-001"

reqs = extract_requirements(tender_pages)
matched_reqs = match_evidence(
    reqs,
    evidence_pages,
    [{"filename": evidence_path.name, "path": str(evidence_path), "asset_id": "EVD-001"}]
)

print(f"Total requirements: {len(matched_reqs)}")
fatal_or_high = [r for r in matched_reqs if r["category"] in {"FATAL", "QUALIFICATION", "SIGNATURE"}]
print(f"FATAL/QUALIFICATION/SIGNATURE items: {len(fatal_or_high)}")

for r in matched_reqs:
    evd_count = len(r.get("evidence", []))
    status = r.get("status")
    # print items of interest
    if r["source"]["page"] in [5, 7, 8, 12, 30]:
        print(f"\n--- [p.{r['source']['page']}] {r['requirement_id']} [{r['category']}] Status: {status} ---")
        print(f"Req quote: {r['source']['quote'][:100]}")
        if r.get("evidence"):
            for e in r["evidence"]:
                print(f"  -> Evidence p.{e['page']}: {e['quote'][:100]}")
        else:
            print("  -> NO EVIDENCE MATCHED (UNKNOWN)")

