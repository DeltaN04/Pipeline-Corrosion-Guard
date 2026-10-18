"""Test that ground_truth.py does not import src.tools.risk (guards against circularity)."""
import ast
from pathlib import Path


def test_ground_truth_no_risk_import():
    """Ensure ground_truth.py has no dependency on src.tools.risk."""
    gt_path = Path(__file__).resolve().parent.parent / "data" / "ground_truth.py"
    with open(gt_path) as f:
        tree = ast.parse(f.read(), filename=str(gt_path))

    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "src.tools.risk" in node.module:
                forbidden.append(f"ImportFrom: {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "risk" in alias.name and "src.tools" in alias.name:
                    forbidden.append(f"Import: {alias.name}")

    assert not forbidden, f"ground_truth.py imports risk module: {forbidden}"