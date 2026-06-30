import argparse
import json
import re
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(password|api[_-]?key|secret|token)\s*[:=]\s*\S+"),
]


def has_secret(value: str) -> bool:
    return any(pattern.search(value or "") for pattern in SECRET_PATTERNS)


def clean_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in (value or "").strip().splitlines()).strip()


def valid_example(example: dict) -> bool:
    required = ("system", "user", "assistant")
    if not all(clean_text(example.get(key, "")) for key in required):
        return False
    joined = "\n".join(str(example.get(key, "")) for key in required)
    if has_secret(joined):
        return False
    metadata = example.get("metadata") or {}
    if metadata.get("quality_score", 1.0) < 0.7:
        return False
    if metadata.get("trainable_memory") is False:
        return False
    return True


def normalize(example: dict) -> dict:
    return {
        "system": clean_text(example["system"]),
        "user": clean_text(example["user"]),
        "assistant": clean_text(example["assistant"]),
        "metadata": example.get("metadata") or {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Autonomus AI JSONL training data.")
    parser.add_argument("--input", default="training/data/raw_examples.jsonl")
    parser.add_argument("--output", default="training/data/train.jsonl")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kept = 0
    skipped = 0
    with input_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            example = json.loads(line)
            if not valid_example(example):
                skipped += 1
                continue
            target.write(json.dumps(normalize(example), ensure_ascii=False) + "\n")
            kept += 1

    print(json.dumps({"kept": kept, "skipped": skipped, "output": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
