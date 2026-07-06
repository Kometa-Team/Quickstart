"""Config-import routes: preview, mapped preview, report, confirm.

This blueprint owns the four /import-config/* routes plus their shared
helpers.  They moved out of quickstart.py during the PR-E refactor.

Public surface (used by tests via ``qs_module.<name>`` re-exports):
* _import_preview_json_default
* _coerce_validation_response_payload
* _map_playlist_libraries
* import_config_preview, import_config_report, import_config_preview_mapped,
  import_config_confirm

## File-size note

This file is ~1,080 lines, still above the 600-line soft-limit.  Two
chunks have already moved out:

* :mod:`blueprints.import_config_helpers` -- 12 pure helpers (~240 lines)
* :mod:`blueprints.import_config_bundle` -- upload / zip extraction
  (~230 lines)

The four remaining routes are tightly coupled through a shared
session-cache flow (import_preview_token / import_preview_path /
import_preview_*_url / import_preview_*_token) so splitting them into
separate per-route modules would either duplicate the shared local logic
or require a sub-package with relative imports -- both worse than
keeping them together.  ``import_config_preview`` alone is ~400 lines
(down from ~510 after the bundle extraction); its plex-validation
(~125 lines) and tmdb-validation (~180 lines) blocks are the next
natural sub-extractions.
"""

import json
import os
import secrets
import shutil
from pathlib import Path

from flask import Blueprint, Flask, current_app, jsonify, request, session

from blueprints.import_config_bundle import extract_bundle_upload
from blueprints.import_config_helpers import (  # noqa: F401 (re-exports for tests and legacy callers)
    _coerce_validation_response_payload,
    _import_preview_json_default,
    _map_playlist_libraries,
    _parse_base_plex_libraries,
    _parse_csv_or_list_to_set,
    _parse_plex_credentials_from_base,
    _parse_plex_credentials_from_config,
    _parse_plex_credentials_from_form,
    _parse_tmdb_credentials_from_base,
    _parse_tmdb_credentials_from_config,
    _parse_tmdb_credentials_from_form,
    count_annotated_lines,
)
from modules import assets, bundle_artifacts, database, helpers, importer, persistence, validations
from modules.library_file_entries import _normalize_imported_libraries_payload

bp = Blueprint("import_config_routes", __name__)


# --- routes ---------------------------------------------------------------


@bp.route("/import-config/preview", methods=["POST"])
def import_config_preview():
    def count_comment_lines(text: str) -> int:
        if not isinstance(text, str):
            return 0
        return sum(1 for line in text.splitlines() if line.lstrip().startswith("#"))

    def count_blank_lines(text: str) -> int:
        if not isinstance(text, str):
            return 0
        return sum(1 for line in text.splitlines() if not line.strip())

    upload = request.files.get("file")
    raw_name = request.form.get("config_name")
    config_name = importer.sanitize_config_name(raw_name)
    merge_mode = str(request.form.get("merge_mode") or "").strip().lower() in {"1", "true", "yes", "merge"}
    base_config = (request.form.get("base_config") or "").strip()

    if not upload or not upload.filename:
        return jsonify(success=False, message="No config file uploaded."), 400
    file_name = upload.filename.lower()
    if not file_name.endswith((".yml", ".yaml", ".zip")):
        return jsonify(success=False, message="Only .yml, .yaml, or .zip files are supported."), 400
    if not config_name:
        return jsonify(success=False, message="Config name is required."), 400

    available = database.get_unique_config_names() or []
    if any(name.lower() == config_name.lower() for name in available):
        return jsonify(success=False, message="Config name already exists."), 400
    if merge_mode:
        base_match = next((name for name in available if name.lower() == base_config.lower()), "")
        if not base_match:
            return jsonify(success=False, message="Base config not found. Select an existing config to merge."), 400
        base_config = base_match

    raw_text = upload.read()
    result = extract_bundle_upload(raw_text, file_name)
    if result.error_response:
        return result.error_response
    config_text = result.config_text
    extracted_fonts = result.extracted_fonts
    extracted_dir = result.extracted_dir

    parsed = importer.load_yaml_config(config_text)
    if not parsed:
        if extracted_dir:
            try:
                shutil.rmtree(extracted_dir)
            except OSError:
                pass
        return jsonify(success=False, message="Unable to parse config file."), 400
    if extracted_dir:
        parsed = bundle_artifacts.rewrite_bundle_library_paths(parsed, extracted_dir)
        parsed = bundle_artifacts.rewrite_bundle_overlay_image_paths(parsed, extracted_dir)

    needs_plex = isinstance(parsed.get("libraries"), dict) and bool(parsed.get("libraries"))
    needs_tmdb = isinstance(parsed, dict) and bool(parsed.get("tmdb") or parsed.get("libraries") or parsed.get("collections") or parsed.get("overlays"))
    plex_data = persistence.retrieve_settings("010-plex").get("plex", {})
    movie_names = _parse_csv_or_list_to_set(plex_data.get("tmp_movie_libraries", ""))
    show_names = _parse_csv_or_list_to_set(plex_data.get("tmp_show_libraries", ""))
    plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}

    if needs_plex:
        base_movie_names, base_show_names = (set(), set())
        skip_plex_validation = False
        if merge_mode and base_config:
            base_movie_names, base_show_names = _parse_base_plex_libraries(base_config)
            if base_movie_names or base_show_names:
                movie_names = base_movie_names
                show_names = base_show_names
                plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
                skip_plex_validation = True

        form_plex_url, form_plex_token = _parse_plex_credentials_from_form(request.form or {})
        imported_plex_url, imported_plex_token = _parse_plex_credentials_from_config(parsed)
        base_plex_url, base_plex_token = _parse_plex_credentials_from_base(base_config) if merge_mode else ("", "")
        has_form = bool(form_plex_url and form_plex_token)
        has_imported = bool(imported_plex_url and imported_plex_token)
        has_base = bool(base_plex_url and base_plex_token)
        used_plex_url = ""
        used_plex_token = ""

        if not skip_plex_validation and not has_form and not has_imported and not has_base:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return (
                jsonify(
                    success=False,
                    needs_plex_credentials=True,
                    message=("Plex credentials are required to import library settings. " "Enter a Plex URL and token to continue."),
                    plex_url="",
                    plex_token="",
                ),
                400,
            )

        if not skip_plex_validation:
            plex_result = None
            last_error = None
            if has_form:
                used_plex_url = form_plex_url
                used_plex_token = form_plex_token
                plex_response = validations.validate_plex_server({"plex_url": form_plex_url, "plex_token": form_plex_token})
                plex_result = _coerce_validation_response_payload(plex_response)
                if not plex_result or not plex_result.get("validated"):
                    if isinstance(plex_result, dict):
                        last_error = plex_result.get("error")
                    if extracted_dir:
                        try:
                            shutil.rmtree(extracted_dir)
                        except OSError:
                            pass
                    return (
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or "Plex validation failed. Please enter valid credentials.",
                            plex_url=form_plex_url or "",
                            plex_token=form_plex_token or "",
                        ),
                        400,
                    )
            else:
                candidates = []
                if merge_mode and has_base:
                    candidates.append((base_plex_url, base_plex_token))
                if has_imported:
                    candidates.append((imported_plex_url, imported_plex_token))
                if not candidates:
                    candidates.append((imported_plex_url or base_plex_url, imported_plex_token or base_plex_token))
                for candidate_url, candidate_token in candidates:
                    used_plex_url = candidate_url
                    used_plex_token = candidate_token
                    plex_response = validations.validate_plex_server({"plex_url": used_plex_url, "plex_token": used_plex_token})
                    plex_result = _coerce_validation_response_payload(plex_response)
                    if plex_result and plex_result.get("validated"):
                        last_error = None
                        break
                    if isinstance(plex_result, dict):
                        last_error = plex_result.get("error")
                if not plex_result or not plex_result.get("validated"):
                    if extracted_dir:
                        try:
                            shutil.rmtree(extracted_dir)
                        except OSError:
                            pass
                    return (
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or ("Plex credentials from the import/base config could not be validated. " "Please enter a valid Plex URL and token."),
                            plex_url=imported_plex_url or base_plex_url or "",
                            plex_token=imported_plex_token or base_plex_token or "",
                        ),
                        400,
                    )
        if not skip_plex_validation:
            session["import_preview_plex_url"] = used_plex_url
            session["import_preview_plex_token"] = used_plex_token
        if used_plex_url and used_plex_token:
            plex_block = parsed.get("plex")
            if not isinstance(plex_block, dict):
                plex_block = {}
                parsed["plex"] = plex_block
            plex_block["url"] = used_plex_url
            plex_block["token"] = used_plex_token
        if not skip_plex_validation:
            movie_names = _parse_csv_or_list_to_set(plex_result.get("movie_libraries", []))
            show_names = _parse_csv_or_list_to_set(plex_result.get("show_libraries", []))
            plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
            if not movie_names and not show_names:
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        message="No movie or show libraries found in Plex.",
                    ),
                    400,
                )

    if needs_tmdb:
        form_tmdb_key = _parse_tmdb_credentials_from_form(request.form or {})
        imported_tmdb_key = _parse_tmdb_credentials_from_config(parsed)
        base_tmdb_key = _parse_tmdb_credentials_from_base(base_config) if merge_mode else ""
        has_form = bool(form_tmdb_key)
        has_imported = bool(imported_tmdb_key)
        has_base = bool(base_tmdb_key)
        used_tmdb_key = ""

        if not has_form and not has_imported and not has_base:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return (
                jsonify(
                    success=False,
                    needs_tmdb_credentials=True,
                    message="TMDb API key is required to import metadata settings. Enter a valid TMDb API key to continue.",
                    tmdb_apikey="",
                ),
                400,
            )

        tmdb_result = None
        last_error = None
        if has_form:
            used_tmdb_key = form_tmdb_key
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": form_tmdb_key})
            tmdb_result = _coerce_validation_response_payload(tmdb_response)
            if not tmdb_result or not tmdb_result.get("valid"):
                if isinstance(tmdb_result, dict):
                    last_error = tmdb_result.get("message")
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        needs_tmdb_credentials=True,
                        message=last_error or "TMDb validation failed. Please enter a valid API key.",
                        tmdb_apikey=form_tmdb_key or "",
                    ),
                    400,
                )
        else:
            candidates = []
            if merge_mode and has_base:
                candidates.append(base_tmdb_key)
            if has_imported:
                candidates.append(imported_tmdb_key)
            if not candidates:
                candidates.append(imported_tmdb_key or base_tmdb_key)
            for candidate_key in candidates:
                used_tmdb_key = candidate_key
                tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": used_tmdb_key})
                tmdb_result = _coerce_validation_response_payload(tmdb_response)
                if tmdb_result and tmdb_result.get("valid"):
                    last_error = None
                    break
                if isinstance(tmdb_result, dict):
                    last_error = tmdb_result.get("message")
            if not tmdb_result or not tmdb_result.get("valid"):
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        needs_tmdb_credentials=True,
                        message=last_error or "TMDb API key from the import/base config could not be validated. Please enter a valid key.",
                        tmdb_apikey=imported_tmdb_key or base_tmdb_key or "",
                    ),
                    400,
                )
        session["import_preview_tmdb_apikey"] = used_tmdb_key
        if used_tmdb_key:
            tmdb_block = parsed.get("tmdb")
            if not isinstance(tmdb_block, dict):
                tmdb_block = {}
                parsed["tmdb"] = tmdb_block
            tmdb_block["apikey"] = used_tmdb_key

    try:
        _library_types, library_inference, _ = importer.build_library_type_plan(parsed, movie_names, show_names)
        payload, report = importer.prepare_import_payload(
            parsed,
            movie_names,
            show_names,
        )
        if not payload:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return jsonify(success=False, message="No importable sections found."), 400
        importable_sections = sorted(payload.keys())

        report_lines = list(report.lines)
        if extracted_fonts:
            for font in extracted_fonts:
                report_lines.append(f"imported: bundle.fonts.{font}")
        annotated_report = importer.annotate_yaml_with_report(config_text, report_lines, binary=True)
        comments_count = count_comment_lines(config_text)
        blank_count = count_blank_lines(config_text)
        total_lines = len(config_text.splitlines()) if isinstance(config_text, str) else 0
        annotated_counts = count_annotated_lines(annotated_report)
        diff_count = total_lines - (annotated_counts.get("imported", 0) + annotated_counts.get("not_imported", 0) + blank_count + comments_count)
        line_counts = {
            "imported_lines": annotated_counts.get("imported", 0),
            "not_imported_lines": annotated_counts.get("not_imported", 0),
            "comments": comments_count,
            "blank": blank_count,
            "total": total_lines,
            "diff": diff_count,
        }

        previous_path = session.get("import_preview_path")
        if previous_path:
            try:
                os.remove(previous_path)
            except OSError:
                pass
        previous_dir = session.get("import_preview_bundle_dir")
        if previous_dir:
            try:
                shutil.rmtree(previous_dir)
            except OSError:
                pass

        cache_dir = Path(helpers.CONFIG_DIR) / "import_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(12)
        cache_path = cache_dir / f"import_{token}.json"
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "config_name": config_name,
                    "config_data": parsed,
                    "config_text": config_text,
                    "payload": payload,
                    "bundle_dir": str(extracted_dir) if extracted_dir else None,
                    "fonts_dir": str((extracted_dir / "fonts").resolve()) if extracted_dir and extracted_fonts else None,
                    "fonts": extracted_fonts,
                    "report_lines": report_lines,
                    "report_summary": report.summary(),
                    "annotated_report": annotated_report,
                    "comments_count": comments_count,
                    "line_counts": line_counts,
                    "plex_movie_names": sorted(movie_names) if isinstance(movie_names, (set, list)) else [],
                    "plex_show_names": sorted(show_names) if isinstance(show_names, (set, list)) else [],
                    "merge_mode": merge_mode,
                    "base_config": base_config,
                    "importable_sections": importable_sections,
                },
                handle,
                ensure_ascii=True,
                default=_import_preview_json_default,
            )
    except Exception as exc:
        if extracted_dir:
            try:
                shutil.rmtree(extracted_dir)
            except OSError:
                pass
        helpers.ts_log(f"Import preview failed: {exc}", level="ERROR")
        return jsonify(success=False, message=f"Import preview failed: {exc}"), 500

    session["import_preview_token"] = token
    session["import_preview_path"] = str(cache_path)
    session["import_preview_name"] = config_name
    session["import_preview_bundle_dir"] = str(extracted_dir) if extracted_dir else ""

    lines = list(report_lines)
    max_lines = 500
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines] + [f"skipped: report truncated ({truncated} more lines)"]

    library_mapping = []
    if needs_plex and isinstance(parsed.get("libraries"), dict):
        inference_map = {item.get("name"): item for item in library_inference}
        for lib_name in parsed.get("libraries", {}).keys():
            name = str(lib_name)
            if name in movie_names or name in show_names:
                continue
            info = inference_map.get(lib_name, {})
            library_mapping.append(
                {
                    "name": lib_name,
                    "inferred_type": info.get("type"),
                    "confidence": info.get("confidence"),
                    "movie_score": info.get("movie_score", 0),
                    "show_score": info.get("show_score", 0),
                }
            )

    return jsonify(
        success=True,
        token=token,
        config_name=config_name,
        summary=report.summary(),
        comments_count=comments_count,
        line_counts=line_counts,
        report_lines=lines,
        annotated_report=annotated_report,
        report_url=f"/import-config/report?token={token}",
        library_mapping=library_mapping,
        plex_libraries=plex_libraries,
        merge_mode=merge_mode,
        base_config=base_config,
        importable_sections=importable_sections,
    )


@bp.route("/import-config/report", methods=["GET"])
def import_config_report():
    token = request.args.get("token")
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_name = cached.get("config_name") or "import"
    report_lines = cached.get("report_lines") or []
    summary = cached.get("report_summary") or {}
    annotated_report = cached.get("annotated_report")
    line_counts = cached.get("line_counts") or {}
    imported_count = line_counts.get("imported_lines", summary.get("imported", 0))
    not_imported_count = line_counts.get(
        "not_imported_lines",
        (summary.get("unmapped", 0) + summary.get("skipped", 0)),
    )
    comments_count = line_counts.get("comments", cached.get("comments_count", 0))
    blank_count = line_counts.get("blank", 0)
    total_count = line_counts.get("total", 0)
    diff_count = line_counts.get(
        "diff",
        total_count - (imported_count + not_imported_count + blank_count + comments_count),
    )

    if annotated_report:
        header = [
            f"# Import Report for {config_name}",
            f"# Imported: {imported_count}",
            f"# Not Imported: {not_imported_count}",
            f"# Comments: {comments_count}",
            f"# Blank: {blank_count}",
            f"# Total: {total_count}",
            f"# Diff: {diff_count}",
            "",
        ]
        text = "\n".join(header) + str(annotated_report)
    else:
        header = [
            f"Import Report for {config_name}",
            f"Imported: {imported_count}",
            f"Not Imported: {not_imported_count}",
            f"Comments: {comments_count}",
            f"Blank: {blank_count}",
            f"Total: {total_count}",
            f"Diff: {diff_count}",
            "",
        ]
        text = "\n".join(header + [str(line) for line in report_lines])
    response = current_app.response_class(text, mimetype="text/plain")
    response.headers["Content-Disposition"] = f'attachment; filename="{config_name}_import_report.txt"'
    return response


@bp.route("/import-config/preview-mapped", methods=["POST"])
def import_config_preview_mapped():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    library_mapping = data.get("library_mapping") or {}
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400
    if library_mapping and not isinstance(library_mapping, dict):
        return jsonify(success=False, message="Invalid library mapping."), 400

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_data = cached.get("config_data") or {}
    if not isinstance(config_data, dict):
        config_data = {}
    config_text = cached.get("config_text") or ""

    movie_names = _parse_csv_or_list_to_set(cached.get("plex_movie_names") or [])
    show_names = _parse_csv_or_list_to_set(cached.get("plex_show_names") or [])
    needs_plex = isinstance(config_data.get("libraries"), dict) and bool(config_data.get("libraries"))

    if needs_plex and not movie_names and not show_names:
        plex_url = session.get("import_preview_plex_url") or ""
        plex_token = session.get("import_preview_plex_token") or ""
        if plex_url and plex_token:
            plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
            plex_result = _coerce_validation_response_payload(plex_response)
            if plex_result and plex_result.get("validated"):
                movie_names = _parse_csv_or_list_to_set(plex_result.get("movie_libraries", []))
                show_names = _parse_csv_or_list_to_set(plex_result.get("show_libraries", []))

    plex_lookup = {name: name for name in movie_names}
    plex_lookup.update({name: name for name in show_names})
    plex_names = set(plex_lookup.values())

    mapping_skip_reasons = {}
    alias_map = {}
    mapping_stats = {"mapped": 0, "ignored": 0, "missing": 0, "invalid": 0, "duplicate": 0}
    if isinstance(config_data.get("libraries"), dict):
        mapped_libraries = {}
        used_targets = set()
        for lib_name, lib_cfg in config_data.get("libraries", {}).items():
            name = str(lib_name)
            if name in plex_lookup:
                target = plex_lookup[name]
            else:
                mapped = library_mapping.get(name)
                if mapped is None or str(mapped).strip() == "":
                    mapping_skip_reasons[name] = "Library mapping not provided."
                    mapping_stats["missing"] += 1
                    continue
                mapped = str(mapped).strip()
                if mapped == "__ignore__":
                    mapping_skip_reasons[name] = "Mapping set to ignore library."
                    mapping_stats["ignored"] += 1
                    continue
                if mapped not in plex_lookup:
                    mapping_skip_reasons[name] = "Mapped library not found in Plex."
                    mapping_stats["invalid"] += 1
                    continue
                target = plex_lookup[mapped]

            if target != name:
                alias_map[name] = target

            if target in used_targets:
                mapping_skip_reasons[name] = "Mapped library already assigned to another entry."
                if name not in plex_names:
                    mapping_stats["duplicate"] += 1
                continue
            used_targets.add(target)
            mapped_libraries[target] = lib_cfg
            if name not in plex_names:
                mapping_stats["mapped"] += 1

        config_copy = json.loads(json.dumps(config_data))
        if mapped_libraries:
            config_copy["libraries"] = mapped_libraries
        else:
            config_copy.pop("libraries", None)
    else:
        config_copy = config_data

    _map_playlist_libraries(config_copy, library_mapping, plex_names)

    payload, report = importer.prepare_import_payload(config_copy, movie_names, show_names)
    importable_sections = sorted(payload.keys()) if isinstance(payload, dict) else []
    report_lines = list(report.lines)
    if mapping_skip_reasons:
        seen = set(report_lines)
        for lib_name, reason in mapping_skip_reasons.items():
            if not lib_name:
                continue
            line = f"skipped: libraries.{lib_name} :: {reason}"
            if line not in seen:
                report_lines.append(line)
                seen.add(line)
    if alias_map and isinstance(config_data.get("libraries"), dict):
        alias_lines = []
        seen = set(report_lines)
        for original_name, mapped_name in alias_map.items():
            if not original_name:
                continue
            mapped_name = str(mapped_name).strip()
            if not mapped_name or mapped_name == "__ignore__":
                continue
            if mapped_name == original_name:
                continue
            prefix = f"libraries.{mapped_name}"
            for line in report_lines:
                if not isinstance(line, str) or ":" not in line:
                    continue
                status, rest = line.split(":", 1)
                status = status.strip()
                path = rest.strip()
                suffix = ""
                if " :: " in path:
                    path, reason = path.split(" :: ", 1)
                    path = path.strip()
                    suffix = f" :: {reason}"
                elif status != "imported" and " - " in path:
                    path, reason = path.split(" - ", 1)
                    path = path.strip()
                    suffix = f" - {reason}"
                if path == prefix or path.startswith(prefix + "."):
                    alias_path = f"libraries.{original_name}{path[len(prefix):]}"
                    alias_line = f"{status}: {alias_path}{suffix}"
                    if alias_line not in seen:
                        alias_lines.append(alias_line)
                        seen.add(alias_line)
        if alias_lines:
            report_lines.extend(alias_lines)
    annotated_report = importer.annotate_yaml_with_report(config_text, report_lines, binary=True)
    comments_count = cached.get("comments_count")
    if not isinstance(comments_count, int):
        comments_count = sum(1 for line in str(config_text).splitlines() if line.lstrip().startswith("#"))
    blank_count = sum(1 for line in str(config_text).splitlines() if not line.strip())
    total_lines = len(str(config_text).splitlines())
    annotated_counts = count_annotated_lines(str(annotated_report))
    imported_lines = annotated_counts.get("imported", 0)
    not_imported_lines = annotated_counts.get("not_imported", 0)
    diff_count = total_lines - (imported_lines + not_imported_lines + blank_count + comments_count)
    line_counts = {
        "imported_lines": imported_lines,
        "not_imported_lines": not_imported_lines,
        "comments": comments_count,
        "blank": blank_count,
        "total": total_lines,
        "diff": diff_count,
    }

    cached["payload"] = payload
    cached["report_lines"] = report_lines
    cached["report_summary"] = report.summary()
    cached["annotated_report"] = annotated_report
    cached["comments_count"] = comments_count
    cached["line_counts"] = line_counts
    cached["plex_movie_names"] = sorted(movie_names)
    cached["plex_show_names"] = sorted(show_names)
    cached["importable_sections"] = importable_sections

    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(cached, handle, ensure_ascii=True, default=_import_preview_json_default)

    lines = list(report_lines)
    max_lines = 500
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines] + [f"skipped: report truncated ({truncated} more lines)"]

    mapping_total = sum(mapping_stats.values())
    mapping_summary = mapping_stats if mapping_total else {}

    return jsonify(
        success=True,
        config_name=cached.get("config_name") or "",
        summary=report.summary(),
        comments_count=comments_count,
        line_counts=line_counts,
        report_lines=lines,
        annotated_report=annotated_report,
        mapping_summary=mapping_summary,
        report_url=f"/import-config/report?token={token}",
        importable_sections=importable_sections,
    )


@bp.route("/import-config/confirm", methods=["POST"])
def import_config_confirm():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    library_mapping = data.get("library_mapping") or {}
    raw_merge_mode = data.get("merge_mode")
    base_config = (data.get("base_config") or "").strip()
    merge_sections = data.get("merge_sections")
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400
    if library_mapping and not isinstance(library_mapping, dict):
        return jsonify(success=False, message="Invalid library mapping."), 400

    def _boolish(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "merge", "on"}
        return False

    merge_mode = _boolish(raw_merge_mode)

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_name = cached.get("config_name")
    payload = cached.get("payload") or {}
    config_data = cached.get("config_data") or {}
    bundle_dir = cached.get("bundle_dir")
    fonts_dir = cached.get("fonts_dir")
    fonts = cached.get("fonts") or []
    cached_merge_mode = helpers.booler(cached.get("merge_mode"))
    if not merge_mode:
        merge_mode = cached_merge_mode
    if not base_config:
        base_config = cached.get("base_config") or ""
    if merge_sections is None:
        merge_sections = cached.get("merge_sections")
    if isinstance(merge_sections, str):
        merge_sections = [entry.strip() for entry in merge_sections.split(",") if entry.strip()]
    elif not isinstance(merge_sections, list):
        merge_sections = []
    merge_sections = [str(entry).strip() for entry in merge_sections if str(entry).strip()]
    if not isinstance(config_data, dict):
        config_data = {}
    importable_sections = set(cached.get("importable_sections") or payload.keys())
    selected_sections = set()
    if merge_mode:
        if not base_config:
            return jsonify(success=False, message="Base config is required for merge."), 400
        available = database.get_unique_config_names() or []
        base_match = next((name for name in available if name.lower() == base_config.lower()), "")
        if not base_match:
            return jsonify(success=False, message="Base config not found. Select an existing config to merge."), 400
        base_config = base_match
        if merge_sections:
            selected_sections = {section for section in merge_sections if section in importable_sections}
        else:
            selected_sections = set(importable_sections)
        if "playlist_files" in selected_sections:
            selected_sections.discard("playlist_files")
            selected_sections.add("libraries")
        if not selected_sections:
            return jsonify(success=False, message="Select at least one section to merge."), 400
        selected_config_sections = set(selected_sections)
        if "libraries" in selected_config_sections:
            selected_config_sections.add("playlist_files")
        config_data = {key: value for key, value in config_data.items() if key in selected_config_sections}
    if not config_name:
        return jsonify(success=False, message="Import payload is invalid."), 400

    available = database.get_unique_config_names() or []
    if any(name.lower() == str(config_name).lower() for name in available):
        return jsonify(success=False, message="Config name already exists."), 400

    movie_names = set()
    show_names = set()
    if config_data:
        libraries_payload = config_data.get("libraries")
        needs_plex = isinstance(libraries_payload, dict) and bool(libraries_payload)
        needs_tmdb = isinstance(config_data, dict) and bool(
            config_data.get("tmdb") or config_data.get("libraries") or config_data.get("collections") or config_data.get("overlays")
        )
        if needs_plex:
            skip_plex_validation = False
            if merge_mode and base_config:
                base_movie_names, base_show_names = _parse_base_plex_libraries(base_config)
                if base_movie_names or base_show_names:
                    movie_names = base_movie_names
                    show_names = base_show_names
                    skip_plex_validation = True

            if skip_plex_validation:
                plex_names = set(movie_names) | set(show_names)
                if not plex_names:
                    skip_plex_validation = False
            if skip_plex_validation:
                # Skip Plex validation when base config provides library cache.
                pass
            else:
                plex_url = session.get("import_preview_plex_url") or ""
                plex_token = session.get("import_preview_plex_token") or ""
                if not plex_url or not plex_token:
                    return (
                        jsonify(
                            success=False,
                            message="Plex credentials are required to confirm the import. Re-run Preview Import.",
                        ),
                        400,
                    )

                plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
                plex_result = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
                if not plex_result or not plex_result.get("validated"):
                    error_message = plex_result.get("error") if isinstance(plex_result, dict) else None
                    return (
                        jsonify(
                            success=False,
                            message=error_message or "Plex validation failed. Re-run Preview Import.",
                        ),
                        400,
                    )
                movie_names = _parse_csv_or_list_to_set(plex_result.get("movie_libraries", []))
                show_names = _parse_csv_or_list_to_set(plex_result.get("show_libraries", []))
                if not movie_names and not show_names:
                    return (
                        jsonify(
                            success=False,
                            message="No movie or show libraries found in Plex.",
                        ),
                        400,
                    )
        else:
            plex_data = persistence.retrieve_settings("010-plex").get("plex", {})
            movie_names = _parse_csv_or_list_to_set(plex_data.get("tmp_movie_libraries", ""))
            show_names = _parse_csv_or_list_to_set(plex_data.get("tmp_show_libraries", ""))

        if needs_tmdb:
            tmdb_apikey = session.get("import_preview_tmdb_apikey") or ""
            if not tmdb_apikey:
                return (
                    jsonify(
                        success=False,
                        message="TMDb API key is required to confirm the import. Re-run Preview Import.",
                    ),
                    400,
                )
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": tmdb_apikey})
            tmdb_result = tmdb_response.get_json() if isinstance(tmdb_response, Flask.response_class) else tmdb_response
            if not tmdb_result or not tmdb_result.get("valid"):
                error_message = tmdb_result.get("message") if isinstance(tmdb_result, dict) else None
                return (
                    jsonify(
                        success=False,
                        message=error_message or "TMDb validation failed. Re-run Preview Import.",
                    ),
                    400,
                )

        plex_lookup = {name: name for name in movie_names}
        plex_lookup.update({name: name for name in show_names})
        plex_names = set(plex_lookup.values())

        if isinstance(libraries_payload, dict):
            if needs_plex and not plex_names:
                return (
                    jsonify(
                        success=False,
                        message="Plex libraries are unavailable. Validate Plex and preview the import again.",
                    ),
                    400,
                )

            missing = []
            invalid_targets = []
            duplicates = []
            used_targets = set()
            mapped_libraries = {}

            for lib_name, lib_cfg in libraries_payload.items():
                name = str(lib_name)
                if name in plex_lookup:
                    target = plex_lookup[name]
                else:
                    mapped = library_mapping.get(name)
                    if mapped is None:
                        missing.append(name)
                        continue
                    mapped = str(mapped).strip()
                    if not mapped:
                        missing.append(name)
                        continue
                    if mapped == "__ignore__":
                        continue
                    if mapped not in plex_lookup:
                        invalid_targets.append(mapped)
                        continue
                    target = plex_lookup[mapped]

                if target in used_targets:
                    duplicates.append(target)
                    continue
                used_targets.add(target)
                mapped_libraries[target] = lib_cfg

            if missing:
                return (
                    jsonify(
                        success=False,
                        message=f"Library mapping required for: {', '.join(missing)}",
                    ),
                    400,
                )
            if invalid_targets:
                unique_targets = sorted(set(invalid_targets))
                return (
                    jsonify(
                        success=False,
                        message=f"Invalid Plex libraries selected: {', '.join(unique_targets)}",
                    ),
                    400,
                )
            if duplicates:
                unique_targets = sorted(set(duplicates))
                return (
                    jsonify(
                        success=False,
                        message=f"Multiple imports mapped to the same Plex library: {', '.join(unique_targets)}",
                    ),
                    400,
                )

            if mapped_libraries:
                config_data["libraries"] = mapped_libraries
            else:
                config_data.pop("libraries", None)

        _map_playlist_libraries(config_data, library_mapping, plex_names)

        payload, report = importer.prepare_import_payload(config_data, movie_names, show_names)
        if merge_mode and selected_sections:
            payload = {section: data_blob for section, data_blob in payload.items() if section in selected_sections}
        if not payload:
            return jsonify(success=False, message="No importable sections found."), 400

    if merge_mode and selected_sections:
        payload = {section: data_blob for section, data_blob in payload.items() if section in selected_sections}
    if not payload:
        return jsonify(success=False, message="No importable sections found."), 400

    if "libraries" in payload:
        normalized_libraries_section, normalize_errors = _normalize_imported_libraries_payload(payload.get("libraries"), config_name)
        if normalize_errors:
            return jsonify(success=False, message="Imported library files could not be organized.", errors=normalize_errors), 400
        payload["libraries"] = normalized_libraries_section

    imported_sections = []
    if merge_mode:
        base_sections = database.retrieve_config_sections(base_config)
        if not base_sections:
            return jsonify(success=False, message="Base config has no saved data to merge."), 400
        for entry in base_sections:
            section = entry.get("section")
            data_blob = entry.get("data")
            if not section or data_blob is None:
                continue
            database.save_section_data(
                name=config_name,
                section=section,
                validated=helpers.booler(entry.get("validated")),
                user_entered=helpers.booler(entry.get("user_entered")),
                data=data_blob,
            )
    for section, data_blob in payload.items():
        database.save_section_data(
            name=config_name,
            section=section,
            validated=False,
            user_entered=True,
            data=data_blob,
        )
        imported_sections.append(section)

    fonts_copied = []
    fonts_skipped = []
    fonts_skipped_existing = []
    fonts_skipped_failed = []
    if fonts_dir and fonts:
        config_fonts_dir = helpers.get_custom_fonts_dir(config_name)
        os.makedirs(config_fonts_dir, exist_ok=True)
        for font_name in fonts:
            src_path = os.path.join(fonts_dir, font_name)
            dest_path = os.path.join(str(config_fonts_dir), font_name)
            if os.path.exists(dest_path):
                fonts_skipped.append(font_name)
                fonts_skipped_existing.append(font_name)
                continue
            try:
                shutil.copy2(src_path, dest_path)
                fonts_copied.append(font_name)
            except OSError:
                fonts_skipped.append(font_name)
                fonts_skipped_failed.append(font_name)
        if fonts_copied:
            # PR E bug fix: previously this `global _FONT_CACHE; _FONT_CACHE = {}`
            # created a new module-level global in quickstart.py named _FONT_CACHE
            # that nothing else looked at -- the real cache lives in modules/assets.py.
            # Use the dedicated clear function so font discovery actually re-runs.
            assets.clear_font_cache()

    try:
        os.remove(cache_path)
    except OSError:
        pass
    if bundle_dir:
        try:
            shutil.rmtree(bundle_dir)
        except OSError:
            pass

    session.pop("import_preview_token", None)
    session.pop("import_preview_path", None)
    session.pop("import_preview_name", None)
    session.pop("import_preview_bundle_dir", None)
    session.pop("import_preview_plex_url", None)
    session.pop("import_preview_plex_token", None)
    session.pop("import_preview_tmdb_apikey", None)
    session["config_name"] = config_name
    importable_sections = sorted(str(section) for section in (cached.get("importable_sections") or payload.keys()))
    skipped_sections = sorted(section for section in importable_sections if section not in set(imported_sections))
    report_summary = report.summary() if "report" in locals() else (cached.get("report_summary") or {})
    mapping_values = [str(value).strip() for value in library_mapping.values()] if isinstance(library_mapping, dict) else []
    mapping_summary = {
        "mapped": sum(1 for value in mapping_values if value and value != "__ignore__"),
        "ignored": sum(1 for value in mapping_values if value == "__ignore__"),
    }

    return jsonify(
        success=True,
        config_name=config_name,
        imported_sections=imported_sections,
        skipped_sections=skipped_sections,
        report_summary=report_summary,
        mapping_summary=mapping_summary,
        fonts_copied=fonts_copied,
        fonts_skipped=fonts_skipped,
        fonts_skipped_existing=fonts_skipped_existing,
        fonts_skipped_failed=fonts_skipped_failed,
    )
