from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.request import urlopen, urlretrieve

OPENFDA_DOWNLOAD_MANIFEST = "https://api.fda.gov/download.json"
DAILYMED_ALL_LABELS = "https://dailymed.nlm.nih.gov/dailymed/spl-resources-all-drug-labels.cfm"


def fetch_openfda_label_manifest() -> dict:
    with urlopen(OPENFDA_DOWNLOAD_MANIFEST, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    label = payload.get("results", {}).get("drug", {}).get("label", {})
    partitions = label.get("partitions", []) or []
    parts = [
        {
            "name": part.get("display_name"),
            "url": part.get("file"),
            "records": part.get("records"),
            "size_mb": _to_float(part.get("size_mb")),
        }
        for part in partitions
        if part.get("file")
    ]
    return {
        "source": "openfda_label",
        "export_date": label.get("export_date"),
        "total_records": label.get("total_records"),
        "total_size_mb": sum(part.get("size_mb") or 0 for part in parts),
        "parts": parts,
    }


def fetch_dailymed_label_manifest() -> dict:
    with urlopen(DAILYMED_ALL_LABELS, timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
    items = []
    for match in re.finditer(r'<li data-ddfilter="(?P<kind>[^"]+)">(?P<body>.*?)</li>\s*</ul>', html, re.I | re.S):
        body = match.group("body")
        url_match = re.search(r'href="(?P<url>https://dailymed-data\.nlm\.nih\.gov/public-release-files/[^"]+\.zip)"', body, re.I)
        name_match = re.search(r'>(?P<name>dm_spl_release_[^<]+\.zip)</a>', body, re.I)
        files_match = re.search(r'Number of files:</strong>\s*(?P<files>[0-9,]+)', body, re.I)
        size_match = re.search(r'File size:</strong>\s*(?P<size>[0-9.]+)\s*(?P<unit>GB|MB)', body, re.I)
        if not url_match or not name_match:
            continue
        size_mb = _to_float(size_match.group("size")) if size_match else None
        if size_mb is not None and size_match and size_match.group("unit").upper() == "GB":
            size_mb *= 1024
        items.append(
            {
                "kind": match.group("kind").strip(),
                "name": name_match.group("name"),
                "url": url_match.group("url"),
                "records": int(files_match.group("files").replace(",", "")) if files_match else None,
                "size_mb": size_mb,
            }
        )
    return {
        "source": "dailymed",
        "source_url": DAILYMED_ALL_LABELS,
        "parts": items,
        "total_records": sum(item.get("records") or 0 for item in items),
        "total_size_mb": sum(item.get("size_mb") or 0 for item in items),
    }


def download_parts(parts: list[dict], out_dir: Path, max_parts: int | None = None, progress=None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    selected = parts[:max_parts] if max_parts else parts
    downloaded = []
    total = max(len(selected), 1)
    for index, part in enumerate(selected, start=1):
        url = part["url"]
        target = out_dir / Path(url).name
        if progress:
            progress(int((index - 1) / total * 100), f"Downloading {target.name}")
        if not target.exists() or target.stat().st_size == 0:
            urlretrieve(url, target)
        downloaded.append(target)
    if progress:
        progress(100, f"Downloaded {len(downloaded)} files")
    return downloaded


def _to_float(value: object) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
