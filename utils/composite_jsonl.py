import json
from copy import deepcopy


PART_FIELDS = {
    "path",
    "type",
    "id",
    "folder",
    "index",
    "x",
    "y",
    "xscale",
    "yscale",
    "loop",
    "muted",
    "autoplay",
    "playsinline",
}

SUMMARY_FIELDS = {"version", "motions", "expressions", "import"}
PART_TYPES = {"live2d", "image", "gif", "video"}


def _normalize_slashes(value):
    return str(value).replace("\\", "/")


def _to_number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_int(value):
    number = _to_number(value)
    if number is None or int(number) != number:
        return None
    return int(number)


def _dedupe_keep_order(values):
    result = []
    seen = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _clean_summary(summary):
    result = {}

    version = _to_int(summary.get("version"))
    if version is not None and version >= 1:
        result["version"] = version

    motions = _dedupe_keep_order(summary.get("motions"))
    if motions:
        result["motions"] = motions

    expressions = _dedupe_keep_order(summary.get("expressions"))
    if expressions:
        result["expressions"] = expressions

    import_value = _to_number(summary.get("import"))
    if import_value is not None:
        result["import"] = int(import_value) if int(import_value) == import_value else import_value

    return result


def _requires_version_two(parts):
    for part in parts:
        if any(
            key in part
            for key in ("type", "loop", "muted", "autoplay", "playsinline")
        ):
            return True
    return False


def is_summary_object(obj):
    return isinstance(obj, dict) and "path" not in obj and any(key in obj for key in SUMMARY_FIELDS)


def parse_composite_jsonl(text, source=None):
    diagnostics = []
    parts = []
    summary = {}
    lines = []

    for line_number, raw in enumerate(str(text).splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            lines.append({"kind": "empty", "lineNumber": line_number, "raw": raw})
            continue

        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            diagnostics.append({
                "code": "invalid-json",
                "lineNumber": line_number,
                "line": raw,
                "message": "Line is not valid JSON.",
            })
            lines.append({"kind": "invalid", "lineNumber": line_number, "raw": raw})
            continue

        if not isinstance(obj, dict):
            diagnostics.append({
                "code": "invalid-root",
                "lineNumber": line_number,
                "line": raw,
                "message": "Line must parse to a JSON object.",
            })
            lines.append({"kind": "unknown", "lineNumber": line_number, "raw": raw})
            continue

        if is_summary_object(obj):
            if "version" in obj:
                version = _to_int(obj.get("version"))
                if version is not None and version >= 1:
                    summary["version"] = version

            if "motions" in obj and isinstance(obj.get("motions"), list):
                summary["motions"] = _dedupe_keep_order((summary.get("motions") or []) + obj["motions"])

            if "expressions" in obj and isinstance(obj.get("expressions"), list):
                summary["expressions"] = _dedupe_keep_order((summary.get("expressions") or []) + obj["expressions"])

            if "import" in obj:
                import_value = _to_number(obj.get("import"))
                if import_value is not None:
                    summary["import"] = int(import_value) if int(import_value) == import_value else import_value

            lines.append({"kind": "summary", "lineNumber": line_number, "raw": raw, "summary": deepcopy(obj)})
            continue

        path = obj.get("path")
        if not isinstance(path, str) or not path.strip():
            diagnostics.append({
                "code": "missing-path",
                "lineNumber": line_number,
                "line": raw,
                "message": "Part lines must include a valid path field.",
            })
            lines.append({"kind": "unknown", "lineNumber": line_number, "raw": raw})
            continue

        part = {
            "path": _normalize_slashes(path.strip()),
            "lineNumber": line_number,
        }

        part_type = obj.get("type")
        if isinstance(part_type, str) and part_type.strip().lower() in PART_TYPES:
            part["type"] = part_type.strip().lower()

        for key in ("id", "folder"):
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                part[key] = value.strip()

        for key in ("index", "x", "y", "xscale", "yscale"):
            number = _to_number(obj.get(key))
            if number is None:
                continue
            part[key] = int(number) if key == "index" and int(number) == number else number

        for key in ("loop", "muted", "autoplay", "playsinline"):
            value = obj.get(key)
            if isinstance(value, bool):
                part[key] = value

        parts.append(part)
        lines.append({"kind": "part", "lineNumber": line_number, "raw": raw, "part": deepcopy(part)})

    manifest = {
        "rawText": str(text),
        "parts": parts,
        "summary": _clean_summary(summary),
        "diagnostics": diagnostics,
        "lines": lines,
    }
    if source:
        manifest["source"] = source
    return manifest


def optimize_composite_jsonl(manifest, fill_missing_index=True):
    parts = []
    for index, part in enumerate(manifest.get("parts", [])):
        next_part = {}
        for key, value in part.items():
            if key == "lineNumber":
                continue
            if key == "path":
                next_part["path"] = _normalize_slashes(value)
            else:
                next_part[key] = value
        if fill_missing_index and "index" not in next_part:
            next_part["index"] = index
        parts.append(next_part)

    summary = _clean_summary(manifest.get("summary", {}))
    if "version" not in summary and _requires_version_two(parts):
        summary["version"] = 2

    text = stringify_composite_jsonl(parts, summary)
    optimized = {
        "rawText": text,
        "parts": [dict(part, lineNumber=i + 1) for i, part in enumerate(parts)],
        "summary": dict(summary, **({"lineNumber": len(parts) + 1} if summary else {})),
        "diagnostics": list(manifest.get("diagnostics", [])),
        "lines": [],
        "text": text,
        "changed": text != manifest.get("rawText", ""),
    }
    if manifest.get("source"):
        optimized["source"] = manifest["source"]
    return optimized


def stringify_composite_jsonl(parts, summary=None):
    lines = []
    for part in parts:
        obj = {}
        for key in (
            "path",
            "type",
            "id",
            "folder",
            "index",
            "x",
            "y",
            "xscale",
            "yscale",
            "loop",
            "muted",
            "autoplay",
            "playsinline",
        ):
            if key in part:
                obj[key] = part[key]
        lines.append(json.dumps(obj, ensure_ascii=False))

    summary_obj = _clean_summary(summary or {})
    if summary_obj:
        lines.append(json.dumps(summary_obj, ensure_ascii=False))

    return "\n".join(lines)
