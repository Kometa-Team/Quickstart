import json

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


def test_apply_template_var_normalizers_expands_franchise_collection_template_maps():
    template_vars = {
        "child_movie_overrides": '{"10": ["1891", "1892"]}',
        "child_name_mapping_overrides": '{"10": "Star Wars Skywalker Saga"}',
        "child_order_overrides": '{"10": "01"}',
        "child_url_background_overrides": '{"10": "https://example.com/star-wars-bg.jpg"}',
        "child_file_poster_overrides": '{"10": "C:\\\\Posters\\\\star-wars.jpg"}',
        "child_url_logo_overrides": '{"10": "https://example.com/star-wars-logo.png"}',
        "child_url_square_art_overrides": '{"10": "https://example.com/star-wars-square.png"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "franchise")

    assert template_vars["movie_10"] == ["1891", "1892"]
    assert template_vars["name_mapping_10"] == "Star Wars Skywalker Saga"
    assert template_vars["order_10"] == "01"
    assert template_vars["url_background_10"] == "https://example.com/star-wars-bg.jpg"
    assert template_vars["file_poster_10"] == r"C:\Posters\star-wars.jpg"
    assert template_vars["url_logo_10"] == "https://example.com/star-wars-logo.png"
    assert template_vars["url_square_art_10"] == "https://example.com/star-wars-square.png"
    assert "child_movie_overrides" not in template_vars


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


def test_apply_template_var_normalizers_expands_seasonal_dynamic_child_override_maps():
    template_vars = {
        "child_name_mapping_overrides": '{"halloween": "Spooky Season"}',
        "child_emoji_overrides": '{"halloween": "🎃"}',
        "child_sort_by_overrides": '{"christmas": "title.asc"}',
        "child_delete_collections_named_overrides": '{"halloween": ["Old Halloween Movies"]}',
        "child_tmdb_collection_overrides": '{"halloween": ["185103", "11716"]}',
        "child_tmdb_movie_overrides": '{"halloween": ["23437"]}',
        "child_imdb_list_overrides": '{"years": ["ls066838460"]}',
        "child_imdb_search_overrides": '{"halloween": {"list.any": ["ls546214737"], "limit": 500}}',
        "child_trakt_list_overrides": '{"halloween": ["https://trakt.tv/users/example/lists/halloween"]}',
        "child_mdblist_list_overrides": '{"christmas": ["https://mdblist.com/lists/k0meta/christmas-extravaganza"]}',
        "child_letterboxd_list_overrides": '{"black_history": ["https://letterboxd.com/mardarrius/list/black-is-beautiful/"]}',
        "child_url_logo_overrides": '{"women": "https://example.com/women.png"}',
        "child_radarr_folder_overrides": '{"halloween": "C:\\\\Media\\\\Movies\\\\Halloween"}',
        "child_radarr_tag_overrides": '{"christmas": ["holiday", "christmas"]}',
        "child_item_radarr_tag_overrides": '{"women": ["history"]}',
        "child_radarr_search_overrides": '{"halloween": "false"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "seasonal")

    assert template_vars["name_mapping_halloween"] == "Spooky Season"
    assert template_vars["emoji_halloween"] == "🎃"
    assert template_vars["sort_by_christmas"] == "title.asc"
    assert template_vars["delete_collections_named_halloween"] == ["Old Halloween Movies"]
    assert template_vars["tmdb_collection_halloween"] == ["185103", "11716"]
    assert template_vars["tmdb_movie_halloween"] == ["23437"]
    assert template_vars["imdb_list_years"] == ["ls066838460"]
    assert template_vars["imdb_search_halloween"] == {"list.any": ["ls546214737"], "limit": 500}
    assert template_vars["trakt_list_halloween"] == ["https://trakt.tv/users/example/lists/halloween"]
    assert template_vars["mdblist_list_christmas"] == ["https://mdblist.com/lists/k0meta/christmas-extravaganza"]
    assert template_vars["letterboxd_list_black_history"] == ["https://letterboxd.com/mardarrius/list/black-is-beautiful/"]
    assert template_vars["url_logo_women"] == "https://example.com/women.png"
    assert template_vars["radarr_folder_halloween"] == r"C:\Media\Movies\Halloween"
    assert template_vars["radarr_tag_christmas"] == ["holiday", "christmas"]
    assert template_vars["item_radarr_tag_women"] == ["history"]
    assert template_vars["radarr_search_halloween"] is False
    assert "child_name_mapping_overrides" not in template_vars
    assert "child_imdb_search_overrides" not in template_vars


def test_apply_template_var_normalizers_expands_region_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"North America": "false"}',
        "child_schedule_overrides": '{"Northern Africa": "weekly(sunday)"}',
        "child_name_mapping_overrides": '{"other": "other_regions"}',
        "child_sort_by_overrides": '{"Western Europe": "title.asc"}',
        "child_limit_overrides": '{"Central America": "12"}',
        "child_url_logo_overrides": '{"Southern Europe": "https://example.com/europe.png"}',
        "child_visible_home_overrides": '{"Caribbean": "true"}',
        "child_visible_library_overrides": '{"Caribbean": "false"}',
        "child_visible_shared_overrides": '{"Caribbean": "true"}',
        "child_hub_priority_overrides": '{"Australia and New Zealand": "7"}',
        "child_item_radarr_tag_overrides": '{"North America": ["north", "america"]}',
        "child_item_sonarr_tag_overrides": '{"Eastern Asia": ["anime"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "region")

    assert template_vars["use_North America"] is False
    assert template_vars["schedule_Northern Africa"] == "weekly(sunday)"
    assert template_vars["name_mapping_other"] == "other_regions"
    assert template_vars["sort_by_Western Europe"] == "title.asc"
    assert template_vars["limit_Central America"] == 12
    assert template_vars["url_logo_Southern Europe"] == "https://example.com/europe.png"
    assert template_vars["visible_home_Caribbean"] is True
    assert template_vars["visible_library_Caribbean"] is False
    assert template_vars["visible_shared_Caribbean"] is True
    assert template_vars["hub_priority_Australia and New Zealand"] == "7"
    assert template_vars["item_radarr_tag_North America"] == ["north", "america"]
    assert template_vars["item_sonarr_tag_Eastern Asia"] == ["anime"]


def test_apply_template_var_normalizers_expands_studio_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"A24": "false"}',
        "child_name_overrides": '{"Marvel Studios": "Marvel Films"}',
        "child_summary_overrides": '{"Warner Bros. Pictures": "Warner favorites"}',
        "child_schedule_overrides": '{"Studio Ghibli": "weekly(sunday)"}',
        "child_name_mapping_overrides": '{"Lucasfilm Ltd": "lucasfilm"}',
        "child_sort_by_overrides": '{"Marvel Studios": "title.asc"}',
        "child_limit_overrides": '{"A24": "10"}',
        "child_url_poster_overrides": '{"A24": "https://example.com/a24.jpg"}',
        "child_visible_home_overrides": '{"Pixar": "false"}',
        "child_visible_library_overrides": '{"Pixar": "true"}',
        "child_visible_shared_overrides": '{"Pixar": "false"}',
        "child_hub_priority_overrides": '{"DreamWorks Studios": "3"}',
        "child_item_radarr_tag_overrides": '{"Lucasfilm Ltd": ["space", "saga"]}',
        "child_item_sonarr_tag_overrides": '{"Warner Bros. Pictures": ["prestige"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "studio")

    assert template_vars["use_A24"] is False
    assert template_vars["name_Marvel Studios"] == "Marvel Films"
    assert template_vars["summary_Warner Bros. Pictures"] == "Warner favorites"
    assert template_vars["schedule_Studio Ghibli"] == "weekly(sunday)"
    assert template_vars["name_mapping_Lucasfilm Ltd"] == "lucasfilm"
    assert template_vars["sort_by_Marvel Studios"] == "title.asc"
    assert template_vars["limit_A24"] == 10
    assert template_vars["url_poster_A24"] == "https://example.com/a24.jpg"
    assert template_vars["visible_home_Pixar"] is False
    assert template_vars["visible_library_Pixar"] is True
    assert template_vars["visible_shared_Pixar"] is False
    assert template_vars["hub_priority_DreamWorks Studios"] == "3"
    assert template_vars["item_radarr_tag_Lucasfilm Ltd"] == ["space", "saga"]
    assert template_vars["item_sonarr_tag_Warner Bros. Pictures"] == ["prestige"]


def test_apply_template_var_normalizers_expands_network_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"Apple TV": "false"}',
        "child_name_overrides": '{"HBO Max": "Max Originals"}',
        "child_summary_overrides": '{"Disney+": "Disney network picks"}',
        "child_schedule_overrides": '{"Netflix": "weekly(friday)"}',
        "child_name_mapping_overrides": '{"Apple TV": "apple_tv"}',
        "child_sort_by_overrides": '{"Netflix": "release.desc"}',
        "child_limit_overrides": '{"HBO": "15"}',
        "child_url_background_overrides": '{"HBO": "https://example.com/hbo-bg.jpg"}',
        "child_visible_home_overrides": '{"Showtime": "true"}',
        "child_visible_library_overrides": '{"Showtime": "false"}',
        "child_visible_shared_overrides": '{"Showtime": "true"}',
        "child_hub_priority_overrides": '{"Disney+": "5"}',
        "child_item_sonarr_tag_overrides": '{"Apple TV": ["streaming", "tv"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "network")

    assert template_vars["use_Apple TV"] is False
    assert template_vars["name_HBO Max"] == "Max Originals"
    assert template_vars["summary_Disney+"] == "Disney network picks"
    assert template_vars["schedule_Netflix"] == "weekly(friday)"
    assert template_vars["name_mapping_Apple TV"] == "apple_tv"
    assert template_vars["sort_by_Netflix"] == "release.desc"
    assert template_vars["limit_HBO"] == 15
    assert template_vars["url_background_HBO"] == "https://example.com/hbo-bg.jpg"
    assert template_vars["visible_home_Showtime"] is True
    assert template_vars["visible_library_Showtime"] is False
    assert template_vars["visible_shared_Showtime"] is True
    assert template_vars["hub_priority_Disney+"] == "5"
    assert template_vars["item_sonarr_tag_Apple TV"] == ["streaming", "tv"]


def test_apply_template_var_normalizers_expands_genre_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"Action": "false"}',
        "child_schedule_overrides": '{"Comedy": "weekly(sunday)"}',
        "child_sort_by_overrides": '{"Drama": "title.asc"}',
        "child_limit_overrides": '{"Horror": "25"}',
        "child_minimum_items_overrides": '{"Sci-Fi": "3"}',
        "child_file_poster_overrides": '{"Action": "C:\\\\Posters\\\\action.jpg"}',
        "child_url_poster_overrides": '{"Comedy": "https://example.com/comedy.jpg"}',
        "child_visible_home_overrides": '{"Drama": "true"}',
        "child_item_radarr_tag_overrides": '{"Horror": ["genre", "horror"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "genre")

    assert template_vars["use_Action"] is False
    assert template_vars["schedule_Comedy"] == "weekly(sunday)"
    assert template_vars["sort_by_Drama"] == "title.asc"
    assert template_vars["limit_Horror"] == 25
    assert template_vars["minimum_items_Sci-Fi"] == 3
    assert template_vars["file_poster_Action"] == r"C:\Posters\action.jpg"
    assert template_vars["url_poster_Comedy"] == "https://example.com/comedy.jpg"
    assert template_vars["visible_home_Drama"] is True
    assert template_vars["item_radarr_tag_Horror"] == ["genre", "horror"]


def test_apply_template_var_normalizers_expands_other_chart_dynamic_child_override_maps():
    template_vars = {
        "child_schedule_overrides": '{"metacritic": "weekly(friday)"}',
        "child_sync_mode_overrides": '{"commonsense": "append"}',
        "child_collection_order_overrides": '{"pirated": "custom"}',
        "child_cache_builders_overrides": '{"stevenlu": "2"}',
        "child_file_logo_overrides": '{"commonsense": "C:\\\\Logos\\\\css.png"}',
        "child_radarr_search_overrides": '{"pirated": "false"}',
        "child_sonarr_add_missing_overrides": '{"metacritic": "true"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "other_chart")

    assert template_vars["schedule_metacritic"] == "weekly(friday)"
    assert template_vars["sync_mode_commonsense"] == "append"
    assert template_vars["collection_order_pirated"] == "custom"
    assert template_vars["cache_builders_stevenlu"] == "2"
    assert template_vars["file_logo_commonsense"] == r"C:\Logos\css.png"
    assert template_vars["radarr_search_pirated"] is False
    assert template_vars["sonarr_add_missing_metacritic"] is True


def test_apply_template_var_normalizers_expands_actor_dynamic_child_override_maps():
    template_vars = {
        "child_name_overrides": '{"Tom Hanks": "Hanks Favorites"}',
        "child_tmdb_person_offset_overrides": '{"Tom Hanks": "1"}',
        "child_limit_overrides": '{"Tom Hanks": "50"}',
        "child_file_poster_overrides": '{"Tom Hanks": "C:\\\\Posters\\\\tom-hanks.jpg"}',
        "child_visible_library_overrides": '{"Tom Hanks": "false"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "actor")

    assert template_vars["name_Tom Hanks"] == "Hanks Favorites"
    assert template_vars["tmdb_person_offset_Tom Hanks"] == 1
    assert template_vars["limit_Tom Hanks"] == 50
    assert template_vars["file_poster_Tom Hanks"] == r"C:\Posters\tom-hanks.jpg"
    assert template_vars["visible_library_Tom Hanks"] is False


def test_apply_template_var_normalizers_expands_movie_person_dynamic_child_override_maps():
    examples = [
        ("director", "Christopher Nolan", "Nolan Favorites", "1", r"C:\Posters\nolan.jpg"),
        ("producer", "Kathleen Kennedy", "Kennedy Produced", "2", r"C:\Posters\kennedy.jpg"),
        ("writer", "Charlie Kaufman", "Kaufman Written", "3", r"C:\Posters\kaufman.jpg"),
    ]
    for default_name, person_name, name_override, offset, poster_path in examples:
        template_vars = {
            "child_name_overrides": json.dumps({person_name: name_override}),
            "child_tmdb_person_offset_overrides": json.dumps({person_name: offset}),
            "child_limit_overrides": json.dumps({person_name: "50"}),
            "child_file_poster_overrides": json.dumps({person_name: poster_path}),
            "child_visible_library_overrides": json.dumps({person_name: "false"}),
        }

        output_collections._apply_template_var_normalizers(template_vars, default_name)

        assert template_vars[f"name_{person_name}"] == name_override
        assert template_vars[f"tmdb_person_offset_{person_name}"] == int(offset)
        assert template_vars[f"limit_{person_name}"] == 50
        assert template_vars[f"file_poster_{person_name}"] == poster_path
        assert template_vars[f"visible_library_{person_name}"] is False


def test_apply_template_var_normalizers_expands_year_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"2024": "false"}',
        "child_name_overrides": '{"2024": "Best of This Year"}',
        "child_schedule_overrides": '{"2023": "weekly(sunday)"}',
        "child_sort_by_overrides": '{"2022": "title.asc"}',
        "child_limit_overrides": '{"2021": "12"}',
        "child_minimum_items_overrides": '{"2020": "3"}',
        "child_url_background_overrides": '{"2019": "https://example.com/2019-bg.jpg"}',
        "child_file_logo_overrides": '{"2018": "C:\\\\Logos\\\\2018.png"}',
        "child_visible_home_overrides": '{"2017": "true"}',
        "child_item_radarr_tag_overrides": '{"2016": ["year", "2016"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "year")

    assert template_vars["use_2024"] is False
    assert template_vars["name_2024"] == "Best of This Year"
    assert template_vars["schedule_2023"] == "weekly(sunday)"
    assert template_vars["sort_by_2022"] == "title.asc"
    assert template_vars["limit_2021"] == 12
    assert template_vars["minimum_items_2020"] == 3
    assert template_vars["url_background_2019"] == "https://example.com/2019-bg.jpg"
    assert template_vars["file_logo_2018"] == r"C:\Logos\2018.png"
    assert template_vars["visible_home_2017"] is True
    assert template_vars["item_radarr_tag_2016"] == ["year", "2016"]


def test_apply_template_var_normalizers_expands_decade_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"2020": "false"}',
        "child_summary_overrides": '{"2010": "2010s favorites"}',
        "child_order_overrides": '{"2000": "03"}',
        "child_schedule_overrides": '{"1990": "weekly(friday)"}',
        "child_sort_by_overrides": '{"1980": "critic_rating.desc"}',
        "child_limit_overrides": '{"1970": "25"}',
        "child_url_square_art_overrides": '{"1960": "https://example.com/1960-square.png"}',
        "child_file_background_overrides": '{"1950": "C:\\\\Backgrounds\\\\1950.jpg"}',
        "child_visible_library_overrides": '{"1940": "false"}',
        "child_item_sonarr_tag_overrides": '{"1930": ["decade", "1930s"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "decade")

    assert template_vars["use_2020"] is False
    assert template_vars["summary_2010"] == "2010s favorites"
    assert template_vars["order_2000"] == "03"
    assert template_vars["schedule_1990"] == "weekly(friday)"
    assert template_vars["sort_by_1980"] == "critic_rating.desc"
    assert template_vars["limit_1970"] == 25
    assert template_vars["url_square_art_1960"] == "https://example.com/1960-square.png"
    assert template_vars["file_background_1950"] == r"C:\Backgrounds\1950.jpg"
    assert template_vars["visible_library_1940"] is False
    assert template_vars["item_sonarr_tag_1930"] == ["decade", "1930s"]


def test_apply_template_var_normalizers_expands_language_dynamic_child_override_maps():
    template_vars = {
        "child_use_overrides": '{"en": "false"}',
        "child_name_overrides": '{"en": "English Audio"}',
        "child_summary_overrides": '{"en": "Movies with English audio"}',
        "child_schedule_overrides": '{"fr": "weekly(sunday)"}',
        "child_sort_by_overrides": '{"fr": "title.asc"}',
        "child_limit_overrides": '{"fr": "25"}',
        "child_minimum_items_overrides": '{"fr": "3"}',
        "child_url_background_overrides": '{"en": "https://example.com/en-bg.jpg"}',
        "child_file_logo_overrides": '{"fr": "C:\\\\Logos\\\\fr-audio.png"}',
        "child_visible_home_overrides": '{"en": "true"}',
        "child_hub_priority_overrides": '{"fr": "4"}',
        "child_item_radarr_tag_overrides": '{"en": "audio,english"}',
        "child_item_sonarr_tag_overrides": '{"fr": ["subtitle", "french"]}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "audio_language")

    assert template_vars["use_en"] is False
    assert template_vars["name_en"] == "English Audio"
    assert template_vars["summary_en"] == "Movies with English audio"
    assert template_vars["schedule_fr"] == "weekly(sunday)"
    assert template_vars["sort_by_fr"] == "title.asc"
    assert template_vars["limit_fr"] == 25
    assert template_vars["minimum_items_fr"] == 3
    assert template_vars["url_background_en"] == "https://example.com/en-bg.jpg"
    assert template_vars["file_logo_fr"] == r"C:\Logos\fr-audio.png"
    assert template_vars["visible_home_en"] is True
    assert template_vars["hub_priority_fr"] == "4"
    assert template_vars["item_radarr_tag_en"] == ["audio", "english"]
    assert template_vars["item_sonarr_tag_fr"] == ["subtitle", "french"]


def test_apply_template_var_normalizers_expands_award_year_override_maps():
    template_vars = {
        "child_collection_order_overrides": '{"2024": "release"}',
        "child_image_overrides": '{"2024": "award/oscars/winner/2024"}',
        "child_translation_key_overrides": '{"2024": "oscars_year"}',
        "child_url_logo_overrides": '{"2024": "https://example.com/oscars.png"}',
        "child_radarr_folder_overrides": '{"2024": "C:\\\\Media\\\\Movies\\\\Awards"}',
        "child_radarr_search_overrides": '{"2024": "false"}',
        "child_visible_home_overrides": '{"2024": "true"}',
    }

    output_collections._apply_template_var_normalizers(template_vars, "oscars")

    assert template_vars["collection_order_2024"] == "release"
    assert template_vars["image_2024"] == "award/oscars/winner/2024"
    assert template_vars["translation_key_2024"] == "oscars_year"
    assert template_vars["url_logo_2024"] == "https://example.com/oscars.png"
    assert template_vars["radarr_folder_2024"] == r"C:\Media\Movies\Awards"
    assert template_vars["radarr_search_2024"] is False
    assert template_vars["visible_home_2024"] is True
