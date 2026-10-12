#!/usr/bin/env python3
"""Verify the rendered Pi footer, never model names in conversation text."""
import re
import sys
from decimal import Decimal


def footer(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    for line in reversed(text.splitlines()):
        gauge = re.search(r"\d+(?:\.\d+)?%/(\d+(?:\.\d+)?)([kKmM]?)\b", line)
        model = re.search(r"\(([\w.-]+)\)\s+([\w.:-]+)(?:\s|$)", line)
        if gauge and model:
            scale = {"": 1, "k": 1000, "m": 1000000}[gauge[2].lower()]
            return f"{model[1]}/{model[2]}", int(Decimal(gauge[1]) * scale)
    raise ValueError("provider/model and context window missing from footer")


def main():
    try:
        actual, context = footer(sys.stdin.read())
        expected, minimum = sys.argv[1], int(sys.argv[2])
        if actual != expected and not ("/" not in expected and actual.split("/", 1)[1] == expected):
            raise ValueError(f"requested {expected}, observed {actual} ({context} tokens)")
        if context < minimum:
            raise ValueError(f"{actual}: context {context} below required {minimum} tokens")
        print(f"{actual} {context}")
    except (ValueError, IndexError) as error:
        print(f"delegate: model verification failed: {error}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
