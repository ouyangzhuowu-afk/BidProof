from pathlib import Path


CSS = (Path(__file__).parents[1] / "static" / "style.css").read_text(encoding="utf-8")


def test_detail_content_can_shrink_inside_narrow_viewport():
    assert ".risk-card {" in CSS
    assert "min-width: 0" in CSS.split(".risk-card {", 1)[1].split("}", 1)[0]
    assert "overflow-wrap: anywhere" in CSS


def test_small_phone_content_reserves_space_for_fixed_bottom_navigation():
    small_phone = CSS.split("@media (max-width: 560px)", 1)[1]
    content_rule = small_phone.split(".content {", 1)[1].split("}", 1)[0]
    padding = content_rule.split("padding:", 1)[1].split(";", 1)[0].strip().split()

    assert len(padding) == 3
    assert int(padding[2].removesuffix("px")) >= 94
