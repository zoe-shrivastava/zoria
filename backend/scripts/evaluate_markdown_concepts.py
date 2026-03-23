"""Evaluate markdown -> concepts JSON conversion quality.

Usage:
  python3 backend/scripts/evaluate_markdown_concepts.py \
    --markdown-file /path/to/doc.md \
    --concepts-json-file /path/to/concepts.json \
    --output-file /path/to/report.json
"""

import argparse
import json
from pathlib import Path

from services.concept_evaluation_service import evaluate_markdown_concepts


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate markdown -> concepts JSON accuracy")
    parser.add_argument("--markdown-file", required=True, help="Path to markdown file")
    parser.add_argument("--concepts-json-file", required=True, help="Path to concepts JSON file")
    parser.add_argument("--output-file", required=False, help="Where to write JSON report")
    args = parser.parse_args()

    markdown = _read_text(Path(args.markdown_file))
    concepts_json = _load_json(Path(args.concepts_json_file))
    report = evaluate_markdown_concepts(markdown, concepts_json)

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote report to {out_path}")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
