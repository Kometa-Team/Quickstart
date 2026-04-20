import pytest

MAL_COLLECTION_KEY = "mov-library_anime-collection_myanimelist"


def _template_list():
    return [
        ("001-start.html", "Start"),
        ("010-plex.html", "Plex"),
        ("020-tmdb.html", "TMDb"),
        ("025-libraries.html", "Libraries"),
        ("030-tautulli.html", "Tautulli"),
        ("130-trakt.html", "Trakt"),
        ("140-mal.html", "MyAnimeList"),
        ("150-settings.html", "Settings"),
        ("900-final.html", "Final Validation"),
    ]


def _section_row(section, *, validated=False, user_entered=False, data=None):
    return {
        "section": section,
        "validated": validated,
        "user_entered": user_entered,
        "data": data or {},
    }


@pytest.mark.parametrize(
    "libraries_data, expected_required, expected_fragment",
    # Add future optional-step dependency vectors here (e.g., other optional pages
    # that can become required based on selections in other sections).
    [
        pytest.param(
            {
                "mov-library_anime-library": "Anime",
                MAL_COLLECTION_KEY: True,
            },
            True,
            "MyAnimeList Charts collection enabled",
            id="mal_collection_enabled",
        ),
        pytest.param(
            {
                "sho-library_anime-library": "Anime Shows",
                "sho-library_anime-attribute_mass_user_rating_update_order": '["tmdb", "mal_japanese"]',
            },
            True,
            "mass_user_rating_update order includes mal_japanese",
            id="mal_source_in_order",
        ),
        pytest.param(
            {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-attribute_mass_user_rating_update_mdb_myanimelist": True,
            },
            False,
            "",
            id="mdb_myanimelist_does_not_require_mal",
        ),
    ],
)
def test_mal_dependency_reason_cases(qs_module, libraries_data, expected_required, expected_fragment):
    reasons = qs_module._libraries_data_mal_dependency_reasons(libraries_data)
    assert bool(reasons) is expected_required
    if expected_fragment:
        assert any(expected_fragment in reason for reason in reasons)
    else:
        assert reasons == []


def test_workspace_context_promotes_mal_to_required(monkeypatch, qs_module):
    rows = [
        _section_row(
            "libraries",
            data={
                "libraries": {
                    "mov-library_anime-library": "Anime",
                    MAL_COLLECTION_KEY: True,
                }
            },
        )
    ]

    monkeypatch.setattr(qs_module.database, "retrieve_config_sections", lambda _name: rows)
    ctx = qs_module._build_workspace_status_context("cfg", _template_list(), available_configs=["cfg"])

    assert "140-mal" in ctx["required_keys"]
    assert "140-mal" not in ctx["optional_keys"]
    assert ctx["mal_requirement_reasons"]


def test_workspace_context_keeps_mal_optional_without_dependency(monkeypatch, qs_module):
    rows = [
        _section_row(
            "libraries",
            data={
                "libraries": {
                    "mov-library_movies-library": "Movies",
                    "mov-library_movies-attribute_mass_user_rating_update_mdb_myanimelist": True,
                }
            },
        )
    ]

    monkeypatch.setattr(qs_module.database, "retrieve_config_sections", lambda _name: rows)
    ctx = qs_module._build_workspace_status_context("cfg", _template_list(), available_configs=["cfg"])

    assert "140-mal" not in ctx["required_keys"]
    assert "140-mal" in ctx["optional_keys"]
    assert ctx["mal_requirement_reasons"] == []


def test_optional_skipped_without_changes_stays_unknown(qs_module):
    section_rows = {
        "tautulli": {
            "validated": False,
            "user_entered": False,
            "data": {
                "validation_status": "skipped",
                "validation_reason": "missing_credentials",
            },
        }
    }

    state = qs_module._derive_step_status("030-tautulli", "optional", section_rows, config_exists=True)
    assert state == "unknown"


def test_optional_skipped_with_user_input_stays_unknown(qs_module):
    section_rows = {
        "tautulli": {
            "validated": False,
            "user_entered": True,
            "data": {
                "validation_status": "skipped",
                "validation_reason": "missing_credentials",
            },
        }
    }

    state = qs_module._derive_step_status("030-tautulli", "optional", section_rows, config_exists=True)
    assert state == "unknown"


def test_playlist_never_visited_is_unknown(qs_module):
    state = qs_module._derive_step_status("027-playlist_files", "optional", {}, config_exists=True)
    assert state == "unknown"


def test_playlist_pass_through_no_selection_is_ok(qs_module):
    section_rows = {
        "playlist_files": {
            "validated": False,
            "user_entered": False,
            "data": {
                "validation_status": "skipped",
                "validation_reason": "no_libraries",
                "validation_updated_at": "2026-04-20T10:00:00Z",
                "playlist_files": {"libraries": ""},
            },
        }
    }

    state = qs_module._derive_step_status("027-playlist_files", "optional", section_rows, config_exists=True)
    assert state == "ok"


def test_mal_optional_without_credentials_stays_unknown_even_if_user_entered(qs_module):
    section_rows = {
        "mal": {
            "validated": False,
            "user_entered": True,
            "data": {
                "validation_status": "",
                "validation_reason": "",
                "mal": {
                    "cache_expiration": "60",
                    "code_verifier": "auto-generated",
                    "authorization": {},
                },
            },
        }
    }

    state = qs_module._derive_step_status("140-mal", "optional", section_rows, config_exists=True)
    assert state == "unknown"


def test_mal_optional_without_credentials_ignores_stale_failed_marker(qs_module):
    section_rows = {
        "mal": {
            "validated": False,
            "user_entered": True,
            "data": {
                "validation_status": "failed",
                "validation_reason": "validation_error",
                "mal": {
                    "cache_expiration": "60",
                    "authorization": {"access_token": ""},
                },
            },
        }
    }

    state = qs_module._derive_step_status("140-mal", "optional", section_rows, config_exists=True)
    assert state == "unknown"


def test_mal_optional_with_credentials_and_not_validated_is_warn(qs_module):
    section_rows = {
        "mal": {
            "validated": False,
            "user_entered": True,
            "data": {
                "validation_status": "",
                "validation_reason": "",
                "mal": {
                    "client_id": "abc123",
                    "client_secret": "xyz987",
                    "localhost_url": "http://localhost:7654",
                    "authorization": {},
                },
            },
        }
    }

    state = qs_module._derive_step_status("140-mal", "optional", section_rows, config_exists=True)
    assert state == "warn"


def test_libraries_mal_dependency_hint_endpoint_returns_reasons(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda _target: {"libraries": {}})

    resp = client.post(
        "/libraries_mal_dependency_hint",
        json={
            "source_library_id": "mov-library_anime",
            "source_payload": {
                "mov-library_anime-library": "Anime",
                MAL_COLLECTION_KEY: "true",
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["required"] is True
    assert any("MyAnimeList Charts collection enabled" in reason for reason in payload["reasons"])


def test_libraries_mal_dependency_hint_endpoint_non_mal_source_returns_empty(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda _target: {"libraries": {}})

    resp = client.post(
        "/libraries_mal_dependency_hint",
        json={
            "source_library_id": "mov-library_movies",
            "source_payload": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-attribute_mass_user_rating_update_mdb_myanimelist": "true",
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["required"] is False
    assert payload["reasons"] == []
