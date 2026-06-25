"""Download routes for serving generated Kometa config bundles.

This blueprint owns:

* ``GET /download`` -- serve the current session's YAML config (or a ZIP
  bundle when there are custom fonts or referenced library/overlay-image
  files to ship alongside it).
* ``GET /download_redacted`` -- same, but with secrets redacted via
  ``helpers.redact_sensitive_data`` so the output is safe to share.

Both routes are thin orchestrators over ``modules.bundle_artifacts``.
The actual bundle-building logic lives there.
"""

import io

from flask import Blueprint, flash, redirect, send_file, session, url_for

from modules import bundle_artifacts, helpers

bp = Blueprint("download_routes", __name__)


@bp.route("/download")
def download():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        config_name = session.get("config_name")
        custom_fonts = bundle_artifacts.get_custom_font_files(config_name)
        artifact_files, bundle_yaml = bundle_artifacts.bundle_artifacts_from_yaml(yaml_content, config_name=config_name)
        if custom_fonts or artifact_files:
            bundle = bundle_artifacts.build_config_bundle(
                bundle_yaml,
                "config.yml",
                custom_fonts,
                artifact_files=artifact_files,
                config_name=config_name,
            )
            if bundle:
                bundle_name = f"{bundle_artifacts.safe_bundle_name(config_name)}_config_bundle.zip"
                return send_file(
                    bundle,
                    mimetype="application/zip",
                    as_attachment=True,
                    download_name=bundle_name,
                )
        return send_file(
            io.BytesIO(yaml_content.encode("utf-8")),
            mimetype="text/yaml",
            as_attachment=True,
            download_name="config.yml",
        )
    flash("No configuration to download", "danger")
    return redirect(url_for("step", name="900-kometa"))


@bp.route("/download_redacted")
def download_redacted():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        # Redact sensitive information
        redacted_content = helpers.redact_sensitive_data(yaml_content)

        # Serve the redacted YAML as a file download
        config_name = session.get("config_name")
        custom_fonts = bundle_artifacts.get_custom_font_files(config_name)
        artifact_files, bundle_yaml = bundle_artifacts.bundle_artifacts_from_yaml(redacted_content, config_name=config_name)
        if custom_fonts or artifact_files:
            bundle = bundle_artifacts.build_config_bundle(
                bundle_yaml,
                "config_redacted.yml",
                custom_fonts,
                artifact_files=artifact_files,
                config_name=config_name,
                redacted=True,
            )
            if bundle:
                bundle_name = f"{bundle_artifacts.safe_bundle_name(config_name)}_config_bundle_redacted.zip"
                return send_file(
                    bundle,
                    mimetype="application/zip",
                    as_attachment=True,
                    download_name=bundle_name,
                )
        return send_file(
            io.BytesIO(redacted_content.encode("utf-8")),
            mimetype="text/yaml",
            as_attachment=True,
            download_name="config_redacted.yml",
        )
    flash("No configuration to download", "danger")
    return redirect(url_for("step", name="900-kometa"))
