"""Instagram Contact-sheet parsing derived from inspected Android hierarchy."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping

from IGBot.runtime.context import RuntimeContext


class AndroidContactScraper:
    """Read all rows exposed by Instagram's Contact RecyclerView."""

    _CONTAINER_ID = "contact_options_rv"
    _HEADER_ID = "contact_option_header"
    _VALUE_ID = "contact_option_sub_text"

    def scrape(self, context: RuntimeContext, hierarchy: str) -> Mapping[str, str]:
        root = ET.fromstring(hierarchy)
        container = next(
            (
                node
                for node in root.iter("node")
                if self._suffix(node) == self._CONTAINER_ID
            ),
            None,
        )
        if container is None:
            raise RuntimeError("Contact RecyclerView was not found")

        details: dict[str, str] = {}
        for row in list(container):
            header = self._descendant_text(row, self._HEADER_ID)
            value = self._descendant_text(row, self._VALUE_ID)
            if not header or not value:
                continue
            key = self._key(header)
            details[key] = value
            label = "Phone" if key == "phone" else header
            context.logger.info(f"[Contact] {label} found.")
        return details

    @classmethod
    def _descendant_text(cls, row: ET.Element, identifier: str) -> str:
        node = next(
            (child for child in row.iter("node") if cls._suffix(child) == identifier),
            None,
        )
        return node.get("text", "").strip() if node is not None else ""

    @staticmethod
    def _suffix(node: ET.Element) -> str:
        return node.get("resource-id", "").rsplit("/", 1)[-1].casefold()

    @staticmethod
    def _key(header: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", header.casefold()).strip("_")
        return "phone" if normalized in {"call", "phone"} else normalized
