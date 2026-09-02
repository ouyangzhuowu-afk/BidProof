from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tmp" / "pdfs" / "upload-samples"
TARGET.mkdir(parents=True, exist_ok=True)


def render(pattern: str, pages: list[int], prefix: str) -> None:
    path = next(ROOT.joinpath("work", "uploads").glob(pattern))
    document = fitz.open(path)
    for page_number in pages:
        if page_number > len(document):
            continue
        pixmap = document[page_number - 1].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
        pixmap.save(TARGET / f"{prefix}-p{page_number}.png")
    document.close()


render("*千佛山医院*.pdf", [2, 5, 6], "qfs")
render("招标文件（信息化建设）*.pdf", [3, 5, 17], "xinhua")
render("智慧财务平台*.pdf", [3, 4, 7], "finance")
