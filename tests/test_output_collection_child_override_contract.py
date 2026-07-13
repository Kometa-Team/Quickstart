from modules import output_collections


def test_apply_template_var_normalizers_expands_universe_dynamic_child_override_maps():
    template_vars = {
        "child_url_poster_overrides": '{"avp": "https://example.com/avp.jpg"}',
        "child_schedule_overrides": '{"arrow": "weekly(sunday)"}',
        "child_trakt_list_overrides": '{"trek": ["https://trakt.tv/users/example/lists/star-trek"]}',
        "child_delete_collections_named_overrides": '{"mummy": ["The Mummy Universe"]}',
        "child_radarr_folder_overrides": '{"avp": "C:\\\\Media\\\\Movies"}',
        "child_radarr_search_overrides": '{"avp": "false"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "universe")

    assert template_vars["url_poster_avp"] == "https://example.com/avp.jpg"
    assert template_vars["schedule_arrow"] == "weekly(sunday)"
    assert template_vars["trakt_list_trek"] == ["https://trakt.tv/users/example/lists/star-trek"]
    assert template_vars["delete_collections_named_mummy"] == ["The Mummy Universe"]
    assert template_vars["radarr_folder_avp"] == r"C:\Media\Movies"
    assert template_vars["radarr_search_avp"] is False
    assert "child_url_poster_overrides" not in template_vars
    assert "child_schedule_overrides" not in template_vars


def test_apply_template_var_normalizers_expands_streaming_dynamic_child_override_maps():
    template_vars = {
        "child_schedule_overrides": '{"amc": "weekly(sunday)"}',
        "child_name_mapping_overrides": '{"movistar": "Movistar Originals"}',
        "child_sort_by_overrides": '{"filmin": "title.asc"}',
        "child_delete_collections_named_overrides": '{"appletv": ["Apple TV+ Movies", "Apple TV+ Shows"]}',
        "child_discover_with_overrides": '{"atresplayer": "62|2162"}',
        "child_url_logo_overrides": '{"movistar": "https://example.com/movistar.png"}',
        "child_radarr_folder_overrides": '{"amc": "C:\\\\Media\\\\Movies\\\\AMC"}',
        "child_radarr_tag_overrides": '{"filmin": ["filmin", "euro"]}',
        "child_radarr_monitor_overrides": '{"movistar": "true"}',
        "child_sonarr_monitor_overrides": '{"filmin": "future"}',
        "child_sonarr_search_overrides": '{"atresplayer": "false"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "streaming")

    assert template_vars["schedule_amc"] == "weekly(sunday)"
    assert template_vars["name_mapping_movistar"] == "Movistar Originals"
    assert template_vars["sort_by_filmin"] == "title.asc"
    assert template_vars["delete_collections_named_appletv"] == ["Apple TV+ Movies", "Apple TV+ Shows"]
    assert template_vars["discover_with_atresplayer"] == "62|2162"
    assert template_vars["url_logo_movistar"] == "https://example.com/movistar.png"
    assert template_vars["radarr_folder_amc"] == r"C:\Media\Movies\AMC"
    assert template_vars["radarr_tag_filmin"] == ["filmin", "euro"]
    assert template_vars["radarr_monitor_movistar"] is True
    assert template_vars["sonarr_monitor_filmin"] == "future"
    assert template_vars["sonarr_search_atresplayer"] is False
    assert "child_schedule_overrides" not in template_vars
    assert "child_url_logo_overrides" not in template_vars
