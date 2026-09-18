"""S-A-06: Tree-Edit-Distance Similarity (TEDS) for HTML tables.

Implements ordered-tree TEDS in the PubTabNet sense without extra deps:

  TEDS(T_pred, T_gt) = 1 - TED(T_pred, T_gt) / max(|T_pred|, |T_gt|)

Node labels are HTML tags; ``td``/``th`` labels include NFKC-normalized cell text.
Engineering metric only — never a product PASS.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any


STRUCTURE_TAGS = frozenset({"table", "thead", "tbody", "tfoot", "tr", "td", "th"})


def _norm_cell(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", "", text).lower()


@dataclass
class TreeNode:
    label: str
    children: list[TreeNode] = field(default_factory=list)

    def size(self) -> int:
        return 1 + sum(child.size() for child in self.children)


class _HtmlTableTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root: TreeNode | None = None
        self._stack: list[TreeNode] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered not in STRUCTURE_TAGS:
            return
        if lowered in {"td", "th"}:
            self._buf = []
            node = TreeNode(label=lowered)
        else:
            node = TreeNode(label=lowered)
        if self._stack:
            self._stack[-1].children.append(node)
        else:
            self.root = node
        self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered not in STRUCTURE_TAGS:
            return
        if not self._stack:
            return
        node = self._stack.pop()
        if lowered in {"td", "th"} and self._buf is not None:
            node.label = f"{lowered}:{_norm_cell(''.join(self._buf))}"
            self._buf = None

    def handle_data(self, data: str) -> None:
        if self._buf is not None:
            self._buf.append(data)


def html_to_tree(html_text: str) -> TreeNode | None:
    parser = _HtmlTableTreeParser()
    parser.feed(html_text or "")
    parser.close()
    return parser.root


def _node_key(node: TreeNode) -> tuple[Any, ...]:
    return (node.label, tuple(_node_key(child) for child in node.children))


def _forest_dist_keyed(
    a_nodes: list[TreeNode],
    b_nodes: list[TreeNode],
    memo: dict[tuple[tuple[Any, ...], tuple[Any, ...]], int],
) -> int:
    """Ordered-forest tree-edit distance (insert/delete/rename cost 1)."""
    a_key = tuple(_node_key(n) for n in a_nodes)
    b_key = tuple(_node_key(n) for n in b_nodes)
    cache_key = (a_key, b_key)
    if cache_key in memo:
        return memo[cache_key]
    if not a_nodes and not b_nodes:
        memo[cache_key] = 0
        return 0
    if not a_nodes:
        cost = sum(n.size() for n in b_nodes)
        memo[cache_key] = cost
        return cost
    if not b_nodes:
        cost = sum(n.size() for n in a_nodes)
        memo[cache_key] = cost
        return cost

    a_head, *a_tail = a_nodes
    b_head, *b_tail = b_nodes
    delete = a_head.size() + _forest_dist_keyed(a_tail, b_nodes, memo)
    insert = b_head.size() + _forest_dist_keyed(a_nodes, b_tail, memo)
    rename = (0 if a_head.label == b_head.label else 1) + _forest_dist_keyed(
        a_head.children, b_head.children, memo
    ) + _forest_dist_keyed(a_tail, b_tail, memo)
    cost = min(delete, insert, rename)
    memo[cache_key] = cost
    return cost


def tree_edit_distance(a: TreeNode | None, b: TreeNode | None) -> int:
    if a is None and b is None:
        return 0
    if a is None:
        return b.size() if b is not None else 0
    if b is None:
        return a.size()
    return _forest_dist_keyed([a], [b], {})


def teds(pred_html: str | None, gt_html: str | None) -> float:
    """Return TEDS in [0, 1]. Empty/missing trees score 0 against a non-empty peer."""
    pred_tree = html_to_tree(pred_html or "")
    gt_tree = html_to_tree(gt_html or "")
    if pred_tree is None and gt_tree is None:
        return 1.0
    if pred_tree is None or gt_tree is None:
        return 0.0
    denom = max(pred_tree.size(), gt_tree.size())
    if denom == 0:
        return 1.0
    distance = tree_edit_distance(pred_tree, gt_tree)
    score = 1.0 - (distance / denom)
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score
