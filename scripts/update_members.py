#!/usr/bin/env python3
"""Generate the members section of the static website from the Excel workbook.

Usage:
    python scripts/update_members.py

The workbook is the single data source for non-PI members.  It must contain
these columns, in this order: 姓名, 照片文件名, 个人简介, 职称/身份（可选）, 邮箱（可选）.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

try:
    from PIL import Image, ImageOps
except ImportError:  # The generator still works without optional image optimization.
    Image = None
    ImageOps = None


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "课题组成员"
WORKBOOK = SOURCE_DIR / "照片以及个人简介收集_已排序.xlsx"
MEMBERS_PAGE = ROOT / "members.html"
ASSET_DIR = ROOT / "assets" / "members"
START_MARKER = "<!-- MEMBERS:START -->"
END_MARKER = "<!-- MEMBERS:END -->"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)


@dataclass(frozen=True)
class Member:
    name: str
    photo: str
    bio: str
    role: str = ""
    email: str = ""


def q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def read_members() -> list[Member]:
    if not WORKBOOK.is_file():
        raise FileNotFoundError(f"Workbook not found: {WORKBOOK}")

    with zipfile.ZipFile(WORKBOOK) as archive:
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = [element_text(item) for item in shared_root.findall(q("si"))]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows: list[dict[str, str]] = []
    for row in sheet.findall(f".//{q('row')}"):
        values: dict[str, str] = {}
        for cell in row.findall(q("c")):
            ref = cell.attrib.get("r", "")
            column = re.match(r"([A-Z]+)", ref)
            if not column:
                continue
            key = column.group(1)
            if cell.attrib.get("t") == "s":
                value_node = cell.find(q("v"))
                value = shared[int(value_node.text)] if value_node is not None else ""
            elif cell.attrib.get("t") == "inlineStr":
                value = element_text(cell.find(q("is")))
            else:
                value = element_text(cell.find(q("v")))
            values[key] = value.strip()
        rows.append(values)

    if not rows:
        raise ValueError("The workbook has no rows.")

    members: list[Member] = []
    problems: list[str] = []
    for row_number, row in enumerate(rows[1:], start=2):
        name, photo, bio = row.get("A", ""), row.get("B", ""), row.get("C", "")
        role, email = row.get("D", ""), row.get("E", "")
        if not any((name, photo, bio, role, email)):
            continue
        if not all((name, photo, bio)):
            problems.append(f"row {row_number}: 姓名、照片文件名和个人简介均为必填")
            continue
        if not (SOURCE_DIR / photo).is_file():
            problems.append(f"row {row_number}: photo not found: {photo}")
            continue
        members.append(Member(name=name, photo=photo, bio=bio, role=role, email=email))

    if problems:
        raise ValueError("Workbook validation failed:\n- " + "\n- ".join(problems))
    if not members:
        raise ValueError("No valid member records found.")
    return members


def prepare_photo(source_photo: Path) -> Path:
    """Copy a member photo, or create a compact WebP when Pillow is available."""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    if Image is None or ImageOps is None:
        destination = ASSET_DIR / source_photo.name
        shutil.copy2(source_photo, destination)
        return destination

    destination = ASSET_DIR / f"{source_photo.stem}.webp"
    with Image.open(source_photo) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((900, 900), Image.Resampling.LANCZOS)
        image.save(destination, "WEBP", quality=82, method=6)
    return destination


def render_member(member: Member) -> str:
    source_photo = SOURCE_DIR / member.photo
    destination = prepare_photo(source_photo)

    details = []
    if member.role:
        details.append(f"<p>{html.escape(member.role)}</p>")
    details.append(f"<p>{html.escape(member.bio)}</p>")
    if member.email:
        email = html.escape(member.email)
        details.append(f'<a href="mailto:{email}">{email}</a>')
    image_url = "assets/members/" + quote(destination.name)
    return (
        '            <article class="member-card">'
        f'<img src="{image_url}" alt="{html.escape(member.name)}">'
        f"<div><h3>{html.escape(member.name)}</h3>{''.join(details)}</div>"
        "</article>"
    )


def render_section(members: list[Member]) -> str:
    pi = """            <article class=\"member-card\">
              <img src=\"assets/pi-qian-binzhi.webp\" alt=\"钱斌治教授肖像\">
              <div>
                <h3>钱斌治</h3>
                <p>教授 / 博士生导师</p>
                <a href=\"mailto:qianbinzhi@fudan.edu.cn\">qianbinzhi@fudan.edu.cn</a>
              </div>
            </article>"""
    return "\n".join([START_MARKER, pi, *(render_member(member) for member in members), END_MARKER])


def update_page(members: list[Member]) -> None:
    page = MEMBERS_PAGE.read_text(encoding="utf-8")
    pattern = re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER)
    updated, count = re.subn(pattern, render_section(members), page, flags=re.DOTALL)
    if count != 1:
        raise ValueError("members.html must contain exactly one pair of MEMBERS markers.")
    MEMBERS_PAGE.write_text(updated, encoding="utf-8")

    referenced = {
        Path(unquote(path)).name
        for path in re.findall(r'assets/members/([^"?]+)', updated)
    }
    for generated_photo in ASSET_DIR.iterdir():
        if generated_photo.is_file() and generated_photo.name not in referenced:
            generated_photo.unlink()


def inline_string_cell(reference: str, value: str) -> str:
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>'
        f"{html.escape(value)}"
        "</t></is></c>"
    )


def update_xml_row(xml: str, row_number: int, updates: dict[str, str]) -> str:
    pattern = rf'(<row\b[^>]*\br="{row_number}"[^>]*>)(.*?)(</row>)'
    match = re.search(pattern, xml, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"Workbook is missing row {row_number}.")
    opening, body, closing = match.groups()
    opening = re.sub(r'\bspans="[^"]*"', 'spans="1:5"', opening)
    if 'spans=' not in opening:
        opening = opening[:-1] + ' spans="1:5">'
    for reference, value in updates.items():
        cell_pattern = rf'<c\b[^>]*\br="{re.escape(reference)}"[^>]*>.*?</c>'
        replacement = inline_string_cell(reference, value)
        body, replacements = re.subn(cell_pattern, replacement, body, flags=re.DOTALL)
        if replacements == 0:
            body += replacement
    return xml[: match.start()] + opening + body + closing + xml[match.end() :]


def repair_markup_compatibility(xml: str) -> str:
    """Restore Office namespace prefixes that ElementTree may have renamed."""
    replacements = {
        'xmlns:ns1="http://schemas.openxmlformats.org/markup-compatibility/2006"': 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"',
        'xmlns:ns2="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"': 'xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"',
        'xmlns:ns3="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"': 'xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"',
        'xmlns:ns4="http://schemas.openxmlformats.org/officeDocument/2006/relationships"': 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"',
        'ns1:Ignorable=': 'mc:Ignorable=',
        'ns2:uid=': 'xr:uid=',
        'ns3:dyDescent=': 'x14ac:dyDescent=',
        'ns4:id=': 'r:id=',
    }
    for old, new in replacements.items():
        xml = xml.replace(old, new)
    return re.sub(r'(mc:Ignorable=")[^"]*(")', r'\1x14ac xr\2', xml)


def migrate_workbook() -> None:
    """Convert the original three-column form export into the five-column template."""
    with zipfile.ZipFile(WORKBOOK) as archive:
        files = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    sheet_xml = files["xl/worksheets/sheet1.xml"].decode("utf-8")
    sheet_xml = repair_markup_compatibility(sheet_xml)
    updates = {
        "A1": "姓名",
        "B1": "照片文件名",
        "C1": "个人简介",
        "D1": "职称/身份（可选）",
        "E1": "邮箱（可选）",
        "D2": "青年副研究员 /硕士生导师",
        "E2": "jiaxiwang@fudan.edu.cn",
        "B6": "李静嘉_2026-09-04 10.45.14_IMG_3282_01.png",
        "B12": "微信图片_20260905143202_64_2.jpg",
    }
    header_updates = {reference: value for reference, value in updates.items() if reference[1:] == "1"}
    row2_updates = {reference: value for reference, value in updates.items() if reference[1:] == "2"}
    sheet_xml = update_xml_row(sheet_xml, 1, header_updates)
    sheet_xml = update_xml_row(sheet_xml, 2, row2_updates)
    sheet_xml = update_xml_row(sheet_xml, 6, {"B6": updates["B6"]})
    sheet_xml = update_xml_row(sheet_xml, 12, {"B12": updates["B12"]})
    sheet_xml = re.sub(r'(<dimension\b[^>]*\bref=")[^"]*(")', r'\1A1:E20\2', sheet_xml)
    files["xl/worksheets/sheet1.xml"] = sheet_xml.encode("utf-8")

    with tempfile.NamedTemporaryFile(dir=WORKBOOK.parent, suffix=".xlsx", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, data in files.items():
                archive.writestr(filename, data)
        temp_path.replace(WORKBOOK)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrate-template",
        action="store_true",
        help="add the optional 职称/身份 and 邮箱 columns to the existing workbook",
    )
    args = parser.parse_args()
    if args.migrate_template:
        migrate_workbook()
    members = read_members()
    update_page(members)
    print(f"Updated members.html with {len(members)} members; copied photos to {ASSET_DIR}.")


if __name__ == "__main__":
    main()
