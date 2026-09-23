from pathlib import Path
from typing import Any

from lxml import etree


def _make_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        strip_cdata=False,
    )


def parse_xml(source_path: Path) -> Any:
    return etree.parse(str(source_path), parser=_make_parser()).getroot()


def parse_xml_string(text: str) -> Any:
    return etree.fromstring(text.encode("utf-8"), parser=_make_parser())


def serialize_xml(root: Any) -> str:
    body = etree.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="utf-8"?>\n{body}\n'


def inner_xml(element: Any) -> str:
    """
    Serializes an element's mixed content (text interleaved with inline child
    elements, e.g. Android's `<xliff:g>` or XLIFF's `<g>`/`<x/>`) into one
    string, so translating it doesn't truncate at the first inline tag the
    way `element.text` alone would.
    """
    parts = [element.text or ""]
    parts.extend(etree.tostring(child, encoding="unicode") for child in element)
    return "".join(parts)


def set_inner_xml(element: Any, xml_fragment: str) -> None:
    wrapper = parse_xml_string(f"<_wrap>{xml_fragment}</_wrap>")
    element.text = wrapper.text
    for existing_child in list(element):
        element.remove(existing_child)
    for child in wrapper:
        element.append(child)


def is_cdata(element: Any) -> bool:
    return "<![CDATA[" in etree.tostring(element, encoding="unicode")
