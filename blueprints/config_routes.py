from pathlib import Path

from flask import Blueprint, current_app as app, flash, jsonify, redirect, request, session, url_for

import namesgenerator
from modules import config_management, database, helpers, importer, persistence

bp = Blueprint("config_routes", __name__)


@bp.route("/clear_session", methods=["POST"])
def clear_session():
    data = request.values
    try:
        config_name = data["name"]
        if config_name != session["config_name"]:
            session["config_name"] = config_name
    except KeyError:  # Handle missing `name` key safely
        config_name = session.get("config_name")

    persistence.flush_session_storage(config_name)

    # Send message to toast
    return jsonify(
        {
            "status": "success",
            "message": f"Session storage cleared for '{config_name}'.",
        }
    )


@bp.route("/clear_data/<name>/<section>")
def clear_data_section(name, section):
    database.reset_data(name, section)
    flash("SQLite storage cleared successfully.", "success")
    return redirect(url_for("start"))


@bp.route("/clear_data/<name>")
def clear_data(name):
    database.reset_data(name)
    cleanup = helpers.delete_config_artifacts(name, kometa_root=app.config.get("KOMETA_ROOT", "."))
    for msg in cleanup.get("errors", []):
        helpers.ts_log(msg, level="WARNING")
    flash("SQLite storage cleared successfully.", "success")
    return redirect(url_for("start"))


@bp.route("/switch-config", methods=["POST"])
def switch_config():
    import quickstart

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(success=False, message="Config name is required."), 400

    available = database.get_unique_config_names() or []
    if name not in available:
        return jsonify(success=False, message="Config not found."), 404

    session["config_name"] = name
    try:
        menu_templates = helpers.get_menu_list()
        workspace_status = quickstart._build_workspace_status_context(name, menu_templates, available_configs=available)
    except Exception:
        workspace_status = {}
    return jsonify(success=True, name=name, workspace_status=workspace_status)


@bp.route("/activate-config", methods=["POST"])
def activate_config():
    data = request.get_json(silent=True) or {}
    requested_name = data.get("name")
    name = config_management.sanitize_config_name(requested_name)
    if not name:
        return jsonify(success=False, message="Config name is required."), 400

    available = database.get_unique_config_names() or []
    created = name not in available

    session["config_name"] = name

    if created:
        seed_payload = {
            "start": {"config_name": name},
            "validated_at": helpers.utc_now_iso(),
        }
        database.save_section_data(
            name=name,
            section="start",
            validated=True,
            user_entered=True,
            data=seed_payload,
        )

    return jsonify(success=True, name=name, created=created)


@bp.route("/bulk-delete-configs", methods=["POST"])
def bulk_delete_configs():
    data = request.get_json(silent=True) or {}
    names = data.get("names") or []
    if not isinstance(names, list):
        return jsonify(success=False, message="Invalid request payload."), 400

    cleaned = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    if not cleaned:
        return jsonify(success=False, message="No configs selected."), 400

    available = set(database.get_unique_config_names() or [])
    deleted = []
    for name in cleaned:
        if name in available:
            database.reset_data(name)
            cleanup = helpers.delete_config_artifacts(name, kometa_root=app.config.get("KOMETA_ROOT", "."))
            for msg in cleanup.get("errors", []):
                helpers.ts_log(msg, level="WARNING")
            deleted.append(name)

    remaining = database.get_unique_config_names() or []
    current = session.get("config_name")
    if current in deleted:
        session["config_name"] = remaining[0] if remaining else namesgenerator.get_random_name()
        current = session["config_name"]

    return jsonify(success=True, deleted=deleted, remaining=remaining, current=current)


@bp.route("/orphaned-config-artifacts", methods=["GET"])
def orphaned_config_artifacts():
    result = helpers.list_orphaned_config_artifacts(kometa_root=app.config.get("KOMETA_ROOT", "."))
    status_code = 200 if not result.get("errors") else 500
    return jsonify(success=not bool(result.get("errors")), orphans=result.get("orphans", []), errors=result.get("errors", [])), status_code


@bp.route("/orphaned-config-artifacts/versions", methods=["GET"])
def orphaned_config_artifact_versions():
    name = request.args.get("name")
    normalized = helpers.normalize_config_name_for_storage(name)
    inventory = helpers.list_orphaned_config_artifacts(kometa_root=app.config.get("KOMETA_ROOT", "."))
    if inventory.get("errors"):
        return jsonify(success=False, message="Unable to inspect config storage.", errors=inventory["errors"]), 500

    orphan_names = {item.get("name") for item in inventory.get("orphans", []) if item.get("name")}
    if normalized not in orphan_names:
        return jsonify(success=False, message="Config bundle is not currently orphaned."), 404

    result = helpers.list_orphaned_config_versions(normalized)
    return jsonify(success=True, name=normalized, versions=result.get("versions", []))


@bp.route("/orphaned-config-artifacts/restore", methods=["POST"])
def restore_orphaned_config_artifact():
    import quickstart

    data = request.get_json(silent=True) or {}
    name = helpers.normalize_config_name_for_storage(data.get("name"))
    selected_path = data.get("path")
    if not name or not isinstance(selected_path, str) or not selected_path.strip():
        return jsonify(success=False, message="Config bundle name and version path are required."), 400

    available = database.get_unique_config_names() or []
    if any(existing.lower() == name.lower() for existing in available):
        return jsonify(success=False, message="Config already exists in the database."), 400

    inventory = helpers.list_orphaned_config_artifacts(kometa_root=app.config.get("KOMETA_ROOT", "."))
    if inventory.get("errors"):
        return jsonify(success=False, message="Unable to inspect config storage.", errors=inventory["errors"]), 500

    orphan_names = {item.get("name") for item in inventory.get("orphans", []) if item.get("name")}
    if name not in orphan_names:
        return jsonify(success=False, message="Config bundle is not currently orphaned."), 404

    versions = helpers.list_orphaned_config_versions(name).get("versions", [])
    version_lookup = {entry.get("path"): entry for entry in versions if entry.get("path")}
    if selected_path not in version_lookup:
        return jsonify(success=False, message="Selected version is not available for restore."), 400

    try:
        source_path = Path(selected_path).resolve()
        yaml_text = source_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return jsonify(success=False, message=f"Unable to read the selected config version: {exc}"), 400

    config_data = importer.load_yaml_config(yaml_text)
    if not config_data:
        return jsonify(success=False, message="Selected config version could not be parsed as YAML."), 400

    payload, report = importer.prepare_import_payload(config_data, set(), set())
    if not payload:
        return jsonify(success=False, message="Selected config version has no importable Quickstart sections."), 400

    for section, data_blob in payload.items():
        database.save_section_data(
            name=name,
            section=section,
            validated=False,
            user_entered=True,
            data=data_blob,
        )

    config_dir = Path(helpers.CONFIG_DIR)
    current_file = (config_dir / f"{name}_config.yml").resolve()
    if source_path != current_file:
        helpers.save_to_named_config(yaml_text, name)
    else:
        kometa_config_dir = Path(app.config.get("KOMETA_ROOT", ".")) / "config"
        try:
            kometa_config_dir.mkdir(parents=True, exist_ok=True)
            (kometa_config_dir / current_file.name).write_text(yaml_text, encoding="utf-8")
        except OSError as exc:
            helpers.ts_log(f"Failed to sync restored config to Kometa: {exc}", level="WARNING")

    session["config_name"] = name
    try:
        menu_templates = helpers.get_menu_list()
        workspace_status = quickstart._build_workspace_status_context(name, menu_templates, available_configs=database.get_unique_config_names() or [])
    except Exception:
        workspace_status = {}

    return jsonify(
        success=True,
        config_name=name,
        restored_path=str(source_path),
        imported_sections=sorted(payload.keys()),
        report_summary=report.summary(),
        workspace_status=workspace_status,
    )


@bp.route("/orphaned-config-artifacts/delete", methods=["POST"])
def delete_orphaned_config_artifacts():
    data = request.get_json(silent=True) or {}
    names = data.get("names") or []
    if not isinstance(names, list):
        return jsonify(success=False, message="Invalid request payload."), 400

    selected = [helpers.normalize_config_name_for_storage(name) for name in names if str(name or "").strip()]
    if not selected:
        return jsonify(success=False, message="No orphaned configs selected."), 400

    inventory = helpers.list_orphaned_config_artifacts(kometa_root=app.config.get("KOMETA_ROOT", "."))
    if inventory.get("errors"):
        return jsonify(success=False, message="Unable to inspect config storage.", errors=inventory["errors"]), 500

    orphan_bundles = {item.get("name"): item for item in inventory.get("orphans", []) if isinstance(item, dict) and item.get("name")}
    orphan_names = set(orphan_bundles)
    invalid = [name for name in selected if name not in orphan_names]
    if invalid:
        return jsonify(success=False, message="Only orphaned config bundles can be deleted here.", invalid=invalid), 400

    deleted = []
    errors = []
    for name in selected:
        result = helpers.delete_orphaned_artifact_bundle(orphan_bundles.get(name))
        if result.get("errors"):
            errors.extend(result["errors"])
        else:
            deleted.append(name)

    if errors:
        return jsonify(success=False, deleted=deleted, errors=errors, message="Some orphaned config bundles could not be deleted."), 500

    return jsonify(success=True, deleted=deleted)


@bp.route("/rename-config", methods=["POST"])
def rename_config():
    data = request.get_json(silent=True) or {}
    old_name = str(data.get("old_name", "")).strip()
    new_name = config_management.sanitize_config_name(data.get("new_name"))
    if not old_name or not new_name:
        return jsonify(success=False, message="Config names are required."), 400
    if old_name == new_name:
        return jsonify(success=False, message="New name must be different."), 400

    available = database.get_unique_config_names() or []
    if old_name not in available:
        return jsonify(success=False, message="Config not found."), 404

    for name in available:
        if name.lower() == new_name.lower() and name != old_name:
            return jsonify(success=False, message="Config name already exists."), 400

    file_check = config_management.rename_config_files(old_name, new_name, dry_run=True)
    if not file_check.get("success"):
        return jsonify(success=False, message="Config files are not safe to rename.", details=file_check), 400

    file_result = config_management.rename_config_files(old_name, new_name)
    if not file_result.get("success"):
        return jsonify(success=False, message="Failed to rename config files.", details=file_result), 500

    try:
        update_result = database.rename_config(old_name, new_name)
    except Exception as exc:
        helpers.ts_log(f"Failed to update database during rename: {exc}", level="ERROR")
        rollback = config_management.rename_config_files(new_name, old_name)
        response = {"success": False, "message": "Failed to update database."}
        if app.config["QS_DEBUG"]:
            response["details"] = rollback
        return jsonify(response), 500

    if not update_result.get("success"):
        rollback = config_management.rename_config_files(new_name, old_name)
        response = {"success": False, "message": "Failed to update database."}
        if app.config["QS_DEBUG"]:
            response["details"] = rollback
        return jsonify(response), 500

    if session.get("config_name") == old_name:
        session["config_name"] = new_name

    return jsonify(success=True, old_name=old_name, new_name=new_name, files=file_result)
