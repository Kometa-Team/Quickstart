from __future__ import annotations

from flask import Blueprint, jsonify, request

from modules.external_yaml_editor import (
    EXTERNAL_YAML_KINDS,
    default_external_yaml_location,
    list_external_yaml_folder_files,
    read_external_yaml_file,
    read_remote_external_yaml_source,
    save_external_yaml_file,
    validate_external_yaml_content,
)

bp = Blueprint("external_yaml_routes", __name__)


def _payload():
    return request.get_json(silent=True) or {}


def _request_context(data):
    return {
        "kind": str(data.get("kind") or "").strip(),
        "location": str(data.get("location") or "").strip(),
        "config_name": str(data.get("config_name") or "").strip(),
        "library_id": str(data.get("library_id") or "").strip(),
    }


@bp.route("/external_yaml_file/read", methods=["POST"])
def read_external_yaml():
    data = _payload()
    ctx = _request_context(data)
    try:
        result = read_external_yaml_file(
            ctx["kind"],
            ctx["location"],
            config_name=ctx["config_name"],
            library_id=ctx["library_id"],
        )
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400

    info = EXTERNAL_YAML_KINDS[ctx["kind"]]
    return jsonify(
        success=True,
        kind=ctx["kind"],
        label=info["label"],
        location=result["location"],
        content=result["content"],
        created=result["created"],
        validation=result["validation"],
    )


@bp.route("/external_yaml_file/validate", methods=["POST"])
def validate_external_yaml():
    data = _payload()
    kind = str(data.get("kind") or "").strip()
    content = str(data.get("content") or "")
    if kind not in EXTERNAL_YAML_KINDS:
        return jsonify(success=False, error="Unsupported YAML file type."), 400
    return jsonify(success=True, validation=validate_external_yaml_content(kind, content))


@bp.route("/external_yaml_file/folder_files", methods=["POST"])
def list_external_yaml_folder():
    data = _payload()
    ctx = _request_context(data)
    try:
        result = list_external_yaml_folder_files(ctx["kind"], ctx["location"])
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400
    return jsonify(success=True, **result)


@bp.route("/external_yaml_file/remote_read", methods=["POST"])
def read_remote_external_yaml():
    data = _payload()
    ctx = _request_context(data)
    source_type = str(data.get("source_type") or "").strip().lower()
    try:
        result = read_remote_external_yaml_source(
            ctx["kind"],
            source_type,
            ctx["location"],
            config_name=ctx["config_name"],
            library_id=ctx["library_id"],
        )
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400
    return jsonify(success=True, **result)


@bp.route("/external_yaml_file/save", methods=["POST"])
def save_external_yaml():
    data = _payload()
    ctx = _request_context(data)
    content = str(data.get("content") or "")
    try:
        saved, path, validation = save_external_yaml_file(
            ctx["kind"],
            ctx["location"] or default_external_yaml_location(ctx["kind"], ctx["config_name"], ctx["library_id"]),
            content,
            config_name=ctx["config_name"],
            library_id=ctx["library_id"],
        )
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400

    if not saved:
        return jsonify(success=False, error=validation.get("error") or "YAML could not be saved.", validation=validation), 400

    from modules.external_yaml_editor import display_external_yaml_location

    return jsonify(
        success=True,
        location=display_external_yaml_location(path),
        validation=validation,
        message="Saved." if not validation.get("warnings") else "Saved with schema warnings.",
    )
