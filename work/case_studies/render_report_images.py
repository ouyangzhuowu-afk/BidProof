import pymupdf
from pathlib import Path

pdf_path = Path("outputs/case-studies/public-tender-invalidation-reconstruction-report.pdf")
doc = pymupdf.open(pdf_path)
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=150)
    out_path = Path(f"outputs/case-studies/page-{i+1}.png")
    pix.save(str(out_path))
    print(f"Rendered: {out_path}")

