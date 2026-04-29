"""
Helper functions for the hierarchical task (Aufgaben) tree.

A task node looks like:
{
    "id": str,                  # unique id (e.g. "t1", "t1.1", ...)
    "label": str,               # display label, auto-generated or custom
    "custom_label": bool,       # True if user has set a custom label
    "afb": str,                 # "I" | "II" | "III" | ""
    "max_punkte": float|None,   # only for leaf nodes; None = sum of children
    "numbering_style": str,     # "123" or "abc" — style for CHILDREN of this node
    "children": list            # list of child nodes (same structure)
}

Root-level nodes use the root's numbering_style (default "123").
"""
from __future__ import annotations
import string


# ── Label generation ─────────────────────────────────────────────────────────

def _num_label(index: int, style: str) -> str:
    """Return label for the n-th child (0-based) given a style."""
    if style == "abc":
        return string.ascii_lowercase[index % 26]
    return str(index + 1)


def generate_labels(nodes: list[dict], parent_prefix: str = "", parent_style: str = "123") -> None:
    """
    Recursively assign auto-generated labels to all nodes that have
    custom_label == False.  Mutates nodes in-place.
    """
    for i, node in enumerate(nodes):
        if not node.get("custom_label", False):
            seg = _num_label(i, parent_style)
            node["label"] = (parent_prefix + seg) if parent_prefix else seg
        # Recurse into children using this node's numbering_style
        children = node.get("children", [])
        if children:
            child_style = node.get("numbering_style", "123")
            prefix = node["label"] + "."
            generate_labels(children, parent_prefix=prefix, parent_style=child_style)


# ── Flat leaf list ────────────────────────────────────────────────────────────

def get_leaves(nodes: list[dict]) -> list[dict]:
    """
    Return all leaf nodes (nodes without children) in depth-first order.
    These correspond to the actual score columns.
    """
    result = []
    for node in nodes:
        if node.get("children"):
            result.extend(get_leaves(node["children"]))
        else:
            result.append(node)
    return result


# ── Max points calculation ────────────────────────────────────────────────────

def calc_max(node: dict) -> float:
    """Return the effective max points for a node (sum of leaves below it)."""
    children = node.get("children", [])
    if not children:
        return float(node.get("max_punkte") or 0)
    return sum(calc_max(c) for c in children)


# ── Compatibility: convert legacy flat aufgaben to tree ──────────────────────

def flat_to_tree(aufgaben: list[dict]) -> list[dict]:
    """
    Convert the old flat list format to a single-level tree (no hierarchy).
    Each old task becomes a root-level leaf node.
    """
    nodes = []
    for i, a in enumerate(aufgaben):
        nodes.append({
            "id": f"t{i}",
            "label": a.get("label", str(i + 1)),
            "custom_label": True,
            "afb": a.get("afb", ""),
            "max_punkte": float(a.get("max_punkte") or 0),
            "numbering_style": "123",
            "children": [],
        })
    return nodes


# ── Convert tree back to legacy flat format (for Excel writer compat) ─────────

def tree_to_flat(nodes: list[dict]) -> list[dict]:
    """
    Flatten the tree to the list of leaf nodes as dicts with keys
    label, afb, max_punkte — compatible with the existing Excel writer.
    """
    leaves = get_leaves(nodes)
    return [
        {
            "label": leaf["label"],
            "afb": leaf.get("afb", ""),
            "max_punkte": float(leaf.get("max_punkte") or 0),
        }
        for leaf in leaves
    ]


# ── Serialise / validate incoming tree from JSON ─────────────────────────────

def sanitize_node(node: dict, depth: int = 0) -> dict:
    """
    Validate and sanitize a single node coming from the browser.
    depth: 0 = root, 1 = sub-task, 2 = sub-sub-task (max depth = 2)
    """
    children_raw = node.get("children", [])
    # Limit depth to 2 levels below root (3 levels total: root, sub, sub-sub)
    if depth >= 2:
        children_raw = []

    children = [sanitize_node(c, depth + 1) for c in children_raw]

    return {
        "id": str(node.get("id", ""))[:40],
        "label": str(node.get("label", ""))[:80].strip() or "?",
        "custom_label": bool(node.get("custom_label", False)),
        "afb": str(node.get("afb", "")).strip(),
        "max_punkte": float(node["max_punkte"]) if node.get("max_punkte") not in (None, "") else None,
        "numbering_style": "abc" if node.get("numbering_style") == "abc" else "123",
        "children": children,
    }
