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
