"""Dump and summarize the current Android UI for IGBot development."""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

import uiautomator2 as u2

OUTPUT_FILENAME = "instagram_ui.xml"


def _display_value(value: object | None) -> str:
    text = str(value or "").replace("\r", "\\r").replace("\n", "\\n")
    return text or "Unavailable"


def _visible_nodes(hierarchy: str) -> tuple[ET.Element, ...]:
    root = ET.fromstring(hierarchy)
    return tuple(
        node
        for node in root.iter("node")
        if node.get("visible-to-user", "true").casefold() != "false"
    )


def _print_node_summary(nodes: tuple[ET.Element, ...], *, output: TextIO) -> None:
    print(f"\nVisible nodes ({len(nodes)}):", file=output)
    for index, node in enumerate(nodes, start=1):
        attributes = (
            ("class", node.get("class")),
            ("text", node.get("text")),
            ("content-desc", node.get("content-desc")),
            ("resource-id", node.get("resource-id")),
            ("bounds", node.get("bounds")),
        )
        details = " | ".join(f"{name}={value!r}" for name, value in attributes if value)
        print(f"[{index:03d}] {details or '(no descriptive attributes)'}", file=output)


def inspect_device(
    serial: str | None = None,
    *,
    connector: Callable[[str | None], object] = u2.connect,
    destination: Path | None = None,
    output: TextIO = sys.stdout,
) -> Path:
    """Connect, save the complete hierarchy, and print visible-node details."""
    device = connector(serial)
    connected_serial = getattr(device, "serial", None) or serial
    current = device.app_current() or {}
    hierarchy = device.dump_hierarchy(compressed=False)

    target = destination or Path.cwd() / OUTPUT_FILENAME
    target.write_text(hierarchy, encoding="utf-8")

    print(f"Connected device serial: {_display_value(connected_serial)}", file=output)
    print(
        f"Current foreground package: {_display_value(current.get('package'))}",
        file=output,
    )
    print(f"Current activity: {_display_value(current.get('activity'))}", file=output)
    _print_node_summary(_visible_nodes(hierarchy), output=output)
    print(f"\nHierarchy saved successfully: {target.resolve()}", file=output)
    return target


def _arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the current Android UI hierarchy with UIAutomator2."
    )
    parser.add_argument(
        "serial",
        nargs="?",
        default=os.environ.get("ANDROID_SERIAL"),
        help=(
            "Android device serial. Defaults to ANDROID_SERIAL or UIAutomator2's "
            "automatic single-device selection."
        ),
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run the standalone inspection command."""
    options = _arguments(arguments)
    try:
        inspect_device(options.serial)
    except Exception as error:  # noqa: BLE001 - standalone CLI error boundary
        print(f"UI inspection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
