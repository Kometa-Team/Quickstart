from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_optional_navigation_groups_are_alphabetical():
    navigation = (ROOT / "templates" / "001-navigation.html").read_text(encoding="utf-8")

    assert "('Core Setup', ['001-start', '010-plex', '020-tmdb', '025-libraries'])" in navigation
    assert (
        "('Required by Configuration', ['100-anidb', '067-floppy', '060-mdblist', '140-mal', '050-omdb', "
        "'110-radarr', '120-sonarr', '030-tautulli', '035-tracearr'])" in navigation
    )
    assert "('Preferences', ['150-settings'])" in navigation
    assert "('Media Integrations', ['110-radarr', '120-sonarr', '030-tautulli', '035-tracearr', '088-yamtrack'])" in navigation
    assert "('Metadata and Lists', ['100-anidb', '067-floppy', '040-github', '060-mdblist', '140-mal', '050-omdb', '065-serializd'])" in navigation
    assert "('Notifications', ['087-apprise', '080-gotify', '070-notifiarr', '085-ntfy', '090-webhooks'])" in navigation


def test_optional_navigation_has_grouped_renderer_and_future_service_fallback():
    navigation = (ROOT / "templates" / "001-navigation.html").read_text(encoding="utf-8")
    macros = (ROOT / "templates" / "partials" / "_workspace_macros.html").read_text(encoding="utf-8")

    assert "workspace.grouped_step_group('Optional Services'" in navigation
    assert 'data-step-subgroup="other"' in macros
    assert "template_key not in grouped_keys.values" in macros


def test_live_membership_updates_target_optional_subgroups():
    base_js = (ROOT / "static" / "local-js" / "000-base.js").read_text(encoding="utf-8")
    libraries_js = (ROOT / "static" / "local-js" / "025-libraries.js").read_text(encoding="utf-8")

    assert "groupedDestination(listEl, key)" in base_js
    assert "destination.orderedKeys.indexOf(key)" in base_js
    assert "destination.element.insertBefore(stepLink, nextSibling || null)" in base_js
    assert "appendInOrder(groups.required, requiredKeys, true)" in base_js
    assert "appendInOrder(groups.optional, optionalKeys, true)" in base_js
    assert "data-step-keys" in libraries_js
    assert "destination.insertBefore(stepButton, nextSibling || null)" in libraries_js
