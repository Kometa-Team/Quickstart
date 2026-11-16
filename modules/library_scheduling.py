"""Library schedules and processing modes from Kometa's finalized PR #3700."""

import copy
import json
import re
from datetime import datetime, timedelta, timezone

from modules import helpers

SCHEDULE_SUFFIX = "-top_level_schedule"
CONFIRM_SUFFIX = "-tmp_schedule_compatibility_confirmed"
DAY_NAMES = set("monday mon m tuesday tues tue tu t wednesday wed w thursday thurs thur thu th r friday fri f saturday sat s sunday sun su u".split())


def parse_schedule(value):
    """Decode a form's JSON while preserving legacy expressions and lists."""
    if isinstance(value, str):
        value = value.strip()
        if value.startswith(("[", "{", '"')):
            try:
                return json.loads(value)
            except ValueError:
                raise ValueError("Scheduling rules must contain valid JSON.") from None
    return copy.deepcopy(value)


def validate_mode(value):
    if not isinstance(value, str):
        raise ValueError("Processing mode must be text.")
    if value in {"full", "diff"}:
        return value
    added = re.fullmatch(r"added\((0*[1-9][0-9]*)([mhd]?)\)", value, re.IGNORECASE)
    if added:
        amount, unit = added.groups()
        try:
            datetime.now(timezone.utc) - timedelta(**{{"m": "minutes", "h": "hours"}.get(unit.lower(), "days"): int(amount)})
        except (OverflowError, ValueError):
            raise ValueError("Added duration is too large.") from None
        return value
    index = re.fullmatch(r"index\(([A-Za-z])(?:-([A-Za-z])(#)?)?\)", value)
    if index:
        start, end, _numbers = index.groups()
        if start.lower() > (end or start).lower():
            raise ValueError("Alphabetical range must be ascending, such as A-F.")
        return value
    if re.fullmatch(r"items\(((?:(?:tmdb|tvdb|plex):0*[1-9][0-9]*|imdb:tt[0-9]+))(\|(?:(?:tmdb|tvdb|plex):0*[1-9][0-9]*|imdb:tt[0-9]+))*\)", value):
        return value
    raise ValueError("Choose full, diff, added(7), added(30m), index(A-F#), or items(imdb:tt0133093|plex:42). IDs and durations must be positive.")


def _split_expressions(value):
    parts, start, stack = [], 0, []
    for offset, char in enumerate(value):
        if char in "([":
            stack.append(char)
        elif char in ")]":
            if not stack or stack.pop() != {")": "(", "]": "["}[char]:
                raise ValueError("Schedule parentheses and brackets must be balanced.")
        elif char == "," and not stack:
            parts.append(value[start:offset].strip())
            start = offset + 1
    if stack:
        raise ValueError("Schedule parentheses and brackets must be balanced.")
    parts.append(value[start:].strip())
    return parts


def validate_expression(value, *, in_all=False):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a schedule expression.")
    expression = value.strip().lower()
    for part in _split_expressions(expression):
        if part in {"daily", "day", "never", "non_existing"}:
            continue
        if part.startswith("all[") and part.endswith("]"):
            if in_all or expression.count("all[") > 1 or len(_split_expressions(expression)) > 1:
                raise ValueError("Use one all[...] expression per schedule, without nested all expressions.")
            validate_expression(part[4:-1], in_all=True)
            continue
        match = re.fullmatch(r"(hourly|hour|weekly|week|monthly|month|yearly|year|date|range)(?:\.not)?\(([^()]+)\)", part)
        if not match:
            raise ValueError(f"Unsupported schedule expression: {part or '(blank)'}. See the Kometa scheduling guide.")
        frequency, parameters = match.groups()
        try:
            for parameter in parameters.split("|"):
                if frequency.startswith("week"):
                    if parameter not in DAY_NAMES:
                        raise ValueError
                elif frequency.startswith(("hour", "month")):
                    maximum = 23 if frequency.startswith("hour") else 31
                    minimum = 0 if maximum == 23 else 1
                    values = parameter.split("-")
                    numbers = [31 if item == "last" and maximum == 31 else int(item) for item in values]
                    if len(numbers) not in {1, 2} or not all(minimum <= number <= maximum for number in numbers):
                        raise ValueError
                    if len(numbers) == 2 and ((maximum == 23 and numbers[0] == numbers[1]) or (maximum == 31 and (numbers[0] > numbers[1] or values[0] == "last"))):
                        raise ValueError
                elif frequency == "date":
                    if len(parameters.split("|")) != 1:
                        raise ValueError
                    datetime.strptime(parameter, "%m/%d/%Y")
                elif frequency.startswith("year"):
                    datetime.strptime(f"{parameter}/2000", "%m/%d/%Y")
                elif frequency == "range":
                    endpoints = parameter.split("-")
                    if len(endpoints) != 2:
                        raise ValueError
                    for endpoint in endpoints:
                        datetime.strptime(f"{endpoint}/2000", "%m/%d/%Y")
        except (ValueError, OverflowError):
            raise ValueError(f"Invalid {frequency} values: {parameters}.") from None
    return value


def schedule_errors(value):
    try:
        value = parse_schedule(value)
    except ValueError as exc:
        return [str(exc)]
    if value is None or value == "":
        return []
    entries = value if isinstance(value, list) else [value]
    if not entries:
        return ["Add at least one rule or disable library scheduling."]
    scoped = any(isinstance(entry, dict) for entry in entries)
    errors = []
    for index, entry in enumerate(entries, 1):
        try:
            if scoped:
                if not isinstance(entry, dict) or set(entry) != {"schedule", "mode"}:
                    raise ValueError("Each processing rule must contain only schedule and mode.")
                validate_expression(entry["schedule"])
                validate_mode(entry["mode"])
            else:
                validate_expression(entry)
        except ValueError as exc:
            errors.append(f"Rule {index}: {exc}")
    if isinstance(value, dict):
        errors.append("Processing rules must be an ordered list.")
    return errors


def runtime_support():
    if helpers.get_kometa_install_mode() == "external":
        return {"supported": None, "message": "Confirm that your external Kometa supports library processing modes and schedule exclusions before exporting them."}
    root = helpers.get_kometa_root_path()
    if not (root / "kometa.py").is_file():
        return {"supported": None, "message": "Install or select a recent Kometa runtime before exporting ordered processing rules."}
    try:
        config = (root / "modules" / "config.py").read_text(encoding="utf-8-sig")
        library = (root / "modules" / "library.py").read_text(encoding="utf-8-sig")
        entrypoint = (root / "kometa.py").read_text(encoding="utf-8-sig")
        supported = "schedule_modes" in config and "runtime_mode" in config and "parse_added_duration" in library and "KOMETA_MODE" in entrypoint
    except OSError:
        supported = False
    return {"supported": supported, "message": "" if supported else "Update Kometa to a build with library processing modes. Saved and imported rules are preserved."}


def validate_library_settings(libraries, selected_ids):
    errors = []
    for library_id in selected_ids:
        for message in schedule_errors(libraries.get(library_id + SCHEDULE_SUFFIX)):
            errors.append({"library_id": library_id, "field": "schedule", "message": message})
    return errors


def configuration_errors(config, libraries):
    errors = []
    support = None
    library_entries = config.get("libraries", {}) if isinstance(config, dict) else {}
    if not isinstance(library_entries, dict):
        return errors  # The schema reports invalid library containers.
    settings = config.get("settings", {})
    settings = settings if isinstance(settings, dict) else {}
    for name, entry in library_entries.items():
        value = entry.get("schedule") if isinstance(entry, dict) else None
        errors.extend(f"{name}: {message}" for message in schedule_errors(value))
        entries = value if isinstance(value, list) else [value]
        needs_runtime = any(isinstance(rule, dict) or (isinstance(rule, str) and ".not(" in rule.lower()) for rule in entries)
        if not needs_runtime:
            continue
        support = support or runtime_support()
        confirmed = any(
            value == name and helpers.booler(libraries.get(key[: -len("-library")] + CONFIRM_SUFFIX, False)) for key, value in libraries.items() if key.endswith("-library")
        )
        if support["supported"] is False or (support["supported"] is None and not confirmed):
            errors.append(f"{name}: {support['message']}")
        if any(isinstance(rule, dict) and rule.get("mode") == "diff" for rule in entries) and settings.get("cache") is False:
            errors.append(f"{name}: diff requires Kometa's persistent cache. Enable cache or choose another processing mode.")
    return errors


def validate_command_mode(parts):
    modes = []
    for index, part in enumerate(parts):
        if part == "--mode":
            modes.append(parts[index + 1] if index + 1 < len(parts) else "")
        elif part.startswith("--mode="):
            modes.append(part.split("=", 1)[1])
    if not modes:
        return
    if len(modes) != 1:
        raise ValueError("Specify only one processing-mode override.")
    validate_mode(modes[0].strip("\"'"))
    support = runtime_support()
    if support["supported"] is not True:
        raise ValueError(support["message"])


def extend_config_schema(schema):
    """Update an older cached library schema to the finalized contract.

    Runtime compatibility is checked separately by configuration_errors;
    collection and overlay scheduling schemas remain unchanged.
    """
    definitions = schema.get("definitions", {}).get("library-section", {}).get("patternProperties", {})
    for library in definitions.values():
        properties = library.get("properties", {})
        schedule = properties.get("schedule")
        if not isinstance(schedule, dict) or '"mode"' in json.dumps(schedule):
            continue
        properties["schedule"] = {
            "oneOf": [
                schedule,
                {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["schedule", "mode"],
                        "additionalProperties": False,
                        "properties": {
                            "schedule": {"type": "string"},
                            "mode": {
                                "type": "string",
                                "pattern": r"^(full|diff|[Aa][Dd][Dd][Ee][Dd]\(0*[1-9][0-9]*[mhdMHD]?\)|index\([A-Za-z](-[A-Za-z]#?)?\)|items\(((tmdb|tvdb|plex):0*[1-9][0-9]*|imdb:tt[0-9]+)(\|((tmdb|tvdb|plex):0*[1-9][0-9]*|imdb:tt[0-9]+))*\))$",
                            },
                        },
                    },
                },
            ]
        }
