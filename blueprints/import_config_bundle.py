"""Upload-bundle extraction for the config-import preview flow.

Split out of :mod:`blueprints.import_config_routes` -- the
``import_config_preview`` route used to inline ~100 lines of
zipfile handling that categorized archive members, validated the
bundle shape, wrote font/library/overlay artifacts to a cache
directory, and left ``config_text`` populated for downstream YAML
parsing.  That mega-block is now :func:`extract_bundle_upload`.

## What lives here

Single public entry point :func:`extract_bundle_upload` that
takes the raw upload bytes plus the (already-lowercased) filename
and returns a :class:`BundleExtractionResult` describing either:

* A successful extraction (config_text populated, plus optional
  extracted_dir and extracted_fonts for bundled artifacts), or
* An error response (Flask ``jsonify`` tuple) that the caller
  should return directly.

The route side stays as a thin caller:

.. code-block:: python

    result = extract_bundle_upload(raw_text, file_name)
    if result.error_response:
        return result.error_response
    config_text = result.config_text
    extracted_dir = result.extracted_dir
    extracted_fonts = result.extracted_fonts

## Why a dataclass instead of a tuple?

Four return values, three of them optional, and code paths that
inspect ``error_response`` vs use the payload -- keyword access
reads better than positional unpacking and lets the caller ignore
fields it doesn't need.  The dataclass is a plain
``@dataclass(slots=True)``; no fancy behaviour.
"""

from __future__ import annotations

import os
import secrets
import shutil
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from flask import jsonify

from modules import bundle_artifacts, helpers
from modules.library_file_entries import _is_bundled_library_archive_member


@dataclass(slots=True)
class BundleExtractionResult:
    """Outcome of :func:`extract_bundle_upload`.

    Exactly one of ``config_text`` or ``error_response`` will be
    populated on any given call.  ``extracted_dir`` and
    ``extracted_fonts`` are only set when the upload was a zip
    bundle carrying font/library/overlay artifacts.
    """

    config_text: str = ""
    extracted_dir: Path | None = None
    extracted_fonts: list = field(default_factory=list)
    error_response: tuple | None = None


def extract_bundle_upload(raw_text: bytes, file_name: str) -> BundleExtractionResult:
    """Extract YAML text (and any bundled artifacts) from an upload.

    :param raw_text: raw bytes read from the uploaded file.
    :param file_name: the *lowercased* upload filename, used to
        pick between the zip-bundle and plain-YAML code paths.
    :returns: a :class:`BundleExtractionResult`.  If
        ``.error_response`` is truthy the caller MUST return it
        directly (it's a Flask ``jsonify`` tuple with an
        appropriate 4xx status).  Otherwise ``.config_text`` is
        the YAML text ready for parsing, and ``.extracted_dir`` /
        ``.extracted_fonts`` describe any bundled artifacts that
        were written to disk.
    """
    if file_name.endswith(".zip"):
        return _extract_zip_bundle(raw_text)
    try:
        config_text = raw_text.decode("utf-8")
    except UnicodeDecodeError:
        config_text = raw_text.decode("utf-8", errors="ignore")
    return BundleExtractionResult(config_text=config_text)


def _extract_zip_bundle(raw_text: bytes) -> BundleExtractionResult:
    """Handle the zip-archive branch of :func:`extract_bundle_upload`."""
    extracted_fonts: list = []
    extracted_dir: Path | None = None
    config_text = ""

    try:
        with zipfile.ZipFile(BytesIO(raw_text)) as archive:
            archive_members = archive.namelist()
            unexpected_members = []
            bundled_library_files = []
            bundled_overlay_images = []
            config_files = []
            font_files = []

            for member_name in archive_members:
                normalized_member = bundle_artifacts.normalize_bundle_member_name(member_name)
                if not normalized_member:
                    continue
                if not bundle_artifacts.is_allowed_bundle_member(normalized_member):
                    unexpected_members.append(normalized_member)
                    continue
                if _is_bundled_library_archive_member(normalized_member):
                    bundled_library_files.append(member_name)
                elif bundle_artifacts.is_bundled_overlay_image_archive_member(normalized_member):
                    bundled_overlay_images.append(member_name)
                elif bundle_artifacts.yaml_path_suffix(normalized_member):
                    config_files.append(member_name)
                elif normalized_member.lower().endswith((".ttf", ".otf")):
                    font_files.append(member_name)

            if unexpected_members:
                preview = ", ".join(unexpected_members[:5])
                if len(unexpected_members) > 5:
                    preview += ", ..."
                return BundleExtractionResult(error_response=(jsonify(success=False, message=f"Zip file contains unsupported entries: {preview}"), 400))
            if not config_files:
                return BundleExtractionResult(error_response=(jsonify(success=False, message="No YAML config found in zip file."), 400))
            if len(config_files) > 1:
                return BundleExtractionResult(error_response=(jsonify(success=False, message="Zip file must contain exactly one YAML config."), 400))

            try:
                with archive.open(config_files[0]) as handle:
                    config_text = handle.read().decode("utf-8", errors="ignore")
            except Exception:
                return BundleExtractionResult(error_response=(jsonify(success=False, message="Unable to read config from zip."), 400))

            if font_files or bundled_library_files or bundled_overlay_images:
                cache_dir = Path(helpers.CONFIG_DIR) / "import_cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                extracted_dir = cache_dir / f"bundle_{secrets.token_urlsafe(8)}"
                extracted_dir.mkdir(parents=True, exist_ok=True)
                if font_files:
                    _extract_fonts(archive, font_files, extracted_dir, extracted_fonts)
                _extract_bundled_files(archive, bundled_library_files, extracted_dir)
                _extract_bundled_files(archive, bundled_overlay_images, extracted_dir)
    except Exception:
        return BundleExtractionResult(error_response=(jsonify(success=False, message="Unable to read zip file."), 400))

    return BundleExtractionResult(
        config_text=config_text,
        extracted_dir=extracted_dir,
        extracted_fonts=extracted_fonts,
    )


def _extract_fonts(archive, font_files, extracted_dir: Path, extracted_fonts: list) -> None:
    """Write font files from the archive into ``extracted_dir/fonts/``.

    Handles name collisions by suffixing ``_1``, ``_2``, ... to
    duplicate basenames.  Silently skips fonts that can't be
    extracted -- fonts are optional decoration for the preview.
    Mutates ``extracted_fonts`` with the safe basenames of every
    font that made it to disk.
    """
    fonts_dir = extracted_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    seen_names: set[str] = set()
    for font_name in font_files:
        base_name = os.path.basename(font_name)
        if not base_name:
            continue
        safe_name = base_name
        counter = 1
        while safe_name in seen_names:
            stem, ext = os.path.splitext(base_name)
            safe_name = f"{stem}_{counter}{ext}"
            counter += 1
        seen_names.add(safe_name)
        try:
            with archive.open(font_name) as source:
                target = fonts_dir / safe_name
                with open(target, "wb") as dest:
                    dest.write(source.read())
                extracted_fonts.append(safe_name)
        except Exception:
            continue


def _extract_bundled_files(archive, member_names, extracted_dir: Path) -> None:
    """Write library/overlay files from the archive into ``extracted_dir``.

    Preserves the archive's directory structure (unlike the flat
    ``_extract_fonts``).  Zip-slip protection: any member whose
    resolved target would escape ``extracted_dir`` is silently
    skipped.  Empty and directory members are also skipped.
    """
    resolved_root = extracted_dir.resolve()
    for member_name in member_names:
        normalized_member = str(member_name).replace("\\", "/").lstrip("/")
        if not normalized_member or normalized_member.endswith("/"):
            continue
        target = (extracted_dir / Path(normalized_member)).resolve()
        try:
            target.relative_to(resolved_root)
        except Exception:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with archive.open(member_name) as source, open(target, "wb") as dest:
                dest.write(source.read())
        except Exception:
            continue


def cleanup_bundle_dir(extracted_dir: Path | None) -> None:
    """Silently remove an extracted bundle directory, ignoring errors.

    Used on the error path of the /import-config/preview flow where
    the caller has already committed to returning a 4xx error and
    just needs to release disk space held by ``extract_bundle_upload``'s
    scratch dir.  If ``extracted_dir`` is ``None`` this is a no-op.

    Was previously eight byte-identical inline blocks scattered
    through the plex + tmdb validation paths.
    """
    if not extracted_dir:
        return
    try:
        shutil.rmtree(extracted_dir)
    except OSError:
        pass
