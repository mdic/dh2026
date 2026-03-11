
from __future__ import annotations
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import yaml
from datetime import datetime

def load_info_json(path: Path) -> dict:
    """Load and parse a JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_config(path: Path) -> dict:
    """Load the YAML configuration for metadata mapping."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def as_attr(value: Optional[object]) -> str:
    """Convert value to string, handling None as empty."""
    return "" if value is None else str(value)

def get_clean_text(element: ET.Element) -> str:
    """
    Extracts all text from a tag, merging any nested <s> tags.
    """
    # Join all text parts found inside the element and its children
    full_text = "".join(element.itertext())
    # Clean up whitespaces and newlines
    return " ".join(full_text.split())

def find_best_subtitle(json_path: Path, priority_suffix: str) -> Optional[Path]:
    """
    Locates the corresponding .srv3 file by iterating through the directory.
    This avoids issues with glob() interpreting brackets [] as patterns.
    """
    base_name = json_path.name.replace(".info.json", "")
    folder = json_path.parent

    potential_subs = []

    # Manually iterate to avoid glob pattern issues with brackets []
    for file in folder.iterdir():
        if file.name.startswith(base_name) and file.suffix == ".srv3":
            potential_subs.append(file)

    if not potential_subs:
        return None

    # Look for the priority suffix
    for s in potential_subs:
        if s.name.endswith(priority_suffix):
            return s

    # Fallback to the first found srv3
    return potential_subs[0]

def indent(elem: ET.Element, level: int = 0) -> None:
    """Pretty-print indentation for XML."""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def main():
    parser = argparse.ArgumentParser(description="Process video JSON metadata and SRV3 subtitles into XML.")
    parser.add_argument("-i", "--input", nargs="+", type=Path, required=True,
                        help="Input directories")
    parser.add_argument("-o", "--output", type=Path, default=Path("output_xml"),
                        help="Output directory for generated XML files")
    parser.add_argument("-c", "--config", type=Path, default=Path("config.yaml"),
                        help="YAML config file")
    parser.add_argument("-s", "--subtitles", action="store_true",
                        help="Enable subtitle processing")
    parser.add_argument("--priority", type=str, default=".en-orig.srv3",
                        help="Preferred subtitle suffix")

    args = parser.parse_args()

    if not args.config.exists():
        print(f"[ERROR] Config file not found: {args.config}")
        return
    config = load_config(args.config)
    args.output.mkdir(parents=True, exist_ok=True)

    json_files = []
    for folder in args.input:
        if folder.exists():
            json_files.extend(list(folder.rglob("*.info.json")))

    for json_path in json_files:
        try:
            info = load_info_json(json_path)
        except Exception as e:
            print(f"[WARN] Failed to load JSON {json_path}: {e}")
            continue

        base_filename = json_path.name.replace(".info.json", "")

        # 1. Prepare Metadata Attributes
        text_attrs = {}
        attr_map = config.get("attributes", {})
        for xml_attr, json_key in attr_map.items():
            text_attrs[xml_attr] = as_attr(info.get(json_key))

        if config.get("include_date", False):
            ts = info.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromtimestamp(ts)
                    text_attrs["year"] = str(dt.year)
                    text_attrs["month"] = str(dt.month).zfill(2)
                    text_attrs["day"] = str(dt.day).zfill(2)
                except:
                    pass

        # 2. Subtitle Logic
        utterances = []
        is_ac = "false"
        sub_path = find_best_subtitle(json_path, args.priority) if args.subtitles else None

        if sub_path:
            try:
                # Use a parser that handles potential namespaces
                tree_sub = ET.parse(sub_path)
                sub_root = tree_sub.getroot()

                # Check for 'ac' attribute anywhere in the file to determine if it's Auto-Generated
                for el in sub_root.iter():
                    if 'ac' in el.attrib:
                        is_ac = "true"
                        break

                # Extract <p> tags regardless of namespace
                # {any_namespace}p
                for p in sub_root.iter():
                    if p.tag.endswith('p'):
                        t_attr = p.attrib.get("t", "")
                        clean_text = get_clean_text(p)
                        if clean_text:
                            utterances.append({"t": t_attr, "text": clean_text})

            except Exception as e:
                print(f"[ERROR] Subtitle parsing failed for {sub_path}: {e}")

        text_attrs["is_ac"] = is_ac

        # 3. Build Final XML
        root_el = ET.Element("text", text_attrs)
        for utt in utterances:
            u_el = ET.SubElement(root_el, "u", {"t": utt["t"]})
            u_el.text = utt["text"]

        indent(root_el)
        output_file = args.output / f"{base_filename}.xml"
        tree = ET.ElementTree(root_el)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        print(f"Generated: {output_file.name}")

if __name__ == "__main__":
    main()
