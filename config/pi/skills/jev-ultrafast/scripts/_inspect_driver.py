#!/usr/bin/env python3
"""Runs inside the pinned checkout's venv, under run.py's outer hard timeout.
Observes a page and prints the indexed element table. Never calls TypeSafe or
the text model, never mutates the page (no .command("act") is ever called
here), never prints a raw traceback (see _bounded.safe_error_text).
"""
from __future__ import annotations

import argparse
import sys

from _bounded import EXIT_DONE, EXIT_ERROR, safe_error_text
import _trace

from jev_ultrafast import Agent  # noqa: E402
from jev_ultrafast.model import action_space  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    args = parser.parse_args(argv)

    try:
        with Agent(args.url, args.goal) as agent:
            page = agent.state["page"]
            elements, targets, controls = action_space(page["actions"])
            print(f"url: {_trace.redact_url(page['url'])}")
            print(f"title: {page['title']}")
            print(f"{len(elements)} observed elements, {len(controls)} fixed controls (no model call made):")
            for el in elements:
                ops = ",".join(el.get("operations", []))
                label = el.get("label", "")
                value = el.get("value", "")
                print(f"  [{el['index']}] {el.get('role', '?'):<10} ops={ops or '-':<20} {label!r} value={value!r}")
            for key, ctrl in controls.items():
                print(f"  ({key}) fixed control: {ctrl.get('label', '')!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {safe_error_text(exc)}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_DONE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
