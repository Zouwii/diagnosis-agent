#!/usr/bin/env python3
"""Find an error code or name in an XLSX workbook using only the stdlib."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def column_name(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference.upper())
    return match.group(1) if match else reference


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall(f"{{{MAIN_NS}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")))
    return values


def sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relations.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    result: list[tuple[str, str]] = []
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = targets[rel_id]
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
            posixpath.join("xl", target)
        )
        result.append((sheet.attrib["name"], path))
    return result


def cell_value(cell: ET.Element, strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value_node = cell.find(f"{{{MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell_type == "s":
        try:
            return strings[int(value)]
        except (ValueError, IndexError):
            return value
    if cell_type == "b":
        return "true" if value == "1" else "false"
    return value


def rows(
    archive: zipfile.ZipFile, path: str, strings: list[str]
) -> Iterator[tuple[int, dict[str, str]]]:
    with archive.open(path) as source:
        for _event, element in ET.iterparse(source, events=("end",)):
            if element.tag != f"{{{MAIN_NS}}}row":
                continue
            number = int(element.attrib.get("r", "0"))
            cells: dict[str, str] = {}
            for cell in element.findall(f"{{{MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "")
                cells[column_name(reference)] = cell_value(cell, strings)
            yield number, cells
            element.clear()


def normalized(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search an XLSX workbook for an exact error code or name."
    )
    parser.add_argument("workbook", type=Path)
    parser.add_argument("query", help="Exact error code, key, or error name")
    parser.add_argument("--sheet", help="Search only this exact sheet name")
    parser.add_argument(
        "--column",
        help="Search only one Excel column, for example A or B (default: all columns)",
    )
    args = parser.parse_args()

    if not args.workbook.is_file():
        parser.error(f"workbook not found: {args.workbook}")

    query = normalized(args.query)
    matches: list[dict[str, object]] = []
    try:
        with zipfile.ZipFile(args.workbook) as archive:
            strings = shared_strings(archive)
            available = sheet_paths(archive)
            selected = [item for item in available if not args.sheet or item[0] == args.sheet]
            if args.sheet and not selected:
                names = ", ".join(name for name, _path in available)
                parser.error(f"sheet not found: {args.sheet}; available sheets: {names}")
            wanted_column = args.column.upper() if args.column else None
            for sheet_name, path in selected:
                for number, cells in rows(archive, path, strings):
                    searchable = (
                        {wanted_column: cells.get(wanted_column, "")}
                        if wanted_column
                        else cells
                    )
                    hit_columns = [
                        key for key, value in searchable.items() if normalized(value) == query
                    ]
                    if hit_columns:
                        matches.append(
                            {
                                "sheet": sheet_name,
                                "row": number,
                                "matched_columns": hit_columns,
                                "cells": cells,
                            }
                        )
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as error:
        print(f"failed to read XLSX: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "workbook": str(args.workbook),
                "query": args.query,
                "match_count": len(matches),
                "matches": matches,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if matches else 2


if __name__ == "__main__":
    raise SystemExit(main())
