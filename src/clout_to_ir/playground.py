"""
playground.py – Developer sandbox for local testing

This script demonstrates the complete Clout ➝ IR pipeline.
"""

import logging
import sys
from pathlib import Path

from src.clout_to_ir import convert_clout_to_ir
from src.ir.models import DeploymentModel

# Enable debug logging if needed
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

DEFAULT_PATH = Path("examples/clout.yaml")


def main(path: str | Path = DEFAULT_PATH) -> None:
    try:
        print(f"Parsing: {path}")
        model: DeploymentModel = convert_clout_to_ir(path)
        print(f"\n✅ Parsed DeploymentModel with {len(model.nodes)} nodes")
        for node in model.nodes:
            print(f"- {node.id}: {node.type}")

        print("=== full schema ===")
        print(model.model_dump_json(indent=2))
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    user_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    main(user_path)
