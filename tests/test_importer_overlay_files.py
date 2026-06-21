from modules import importer


def test_prepare_import_payload_maps_multiple_overlay_files_per_library():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {"file": "config/overlays/movies.yml"},
                        {"folder": "config/overlays/movies"},
                        {"git": "bullmoose20/overlays.yml"},
                        {"repo": "custom/movies_overlays.yml"},
                        {"url": "https://example.com/movie-overlays.yml"},
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert "mov-library_movies-overlay_files" in libraries_payload
    assert (
        libraries_payload["mov-library_movies-overlay_files"]
        == '[{"type": "file", "location": "config/overlays/movies.yml"}, {"type": "folder", "location": "config/overlays/movies"}, {"type": "git", "location": "bullmoose20/overlays.yml"}, {"type": "repo", "location": "custom/movies_overlays.yml"}, {"type": "url", "location": "https://example.com/movie-overlays.yml"}]'
    )
    assert any("libraries.Movies.overlay_files[0].file" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[1].folder" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[2].git" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[3].repo" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[4].url" in line for line in report.lines)


def test_prepare_import_payload_accepts_resolution_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "resolution",
                            "template_variables": {
                                "use_resolution": False,
                                "use_edition": True,
                                "use_4k": False,
                                "use_4k_dvhdrplus": False,
                                "use_1080p": False,
                                "use_1080p_dv": False,
                                "use_720p_hdr": False,
                                "use_576p_dvhdr": False,
                                "use_480p_plus": False,
                                "use_dv": False,
                                "use_plus": False,
                                "use_dvhdr": False,
                                "use_extended": False,
                                "use_openmatte": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_resolution"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_resolution]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_edition]"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_4k]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_4k_dvhdrplus]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_1080p]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_1080p_dv]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_720p_hdr]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_576p_dvhdr]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_480p_plus]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_dv]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_plus]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_dvhdr]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_extended]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_openmatte]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_resolution" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_1080p" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_1080p_dv" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_plus" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_extended" in line for line in report.lines)


def test_prepare_import_payload_accepts_audio_codec_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "audio_codec",
                            "template_variables": {
                                "use_truehd_atmos": False,
                                "use_dtsx": False,
                                "use_plus_atmos": False,
                                "use_dolby_atmos": False,
                                "use_truehd": False,
                                "use_ma": False,
                                "use_flac": False,
                                "use_pcm": False,
                                "use_hra": False,
                                "use_plus": False,
                                "use_dtses": False,
                                "use_dts": False,
                                "use_digital": False,
                                "use_aac": False,
                                "use_mp3": False,
                                "use_opus": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_audio_codec"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_truehd_atmos]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_dtsx]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_plus_atmos]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_dolby_atmos]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_truehd]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_ma]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_flac]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_pcm]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_hra]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_plus]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_dtses]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_dts]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_digital]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_aac]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_mp3]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_audio_codec[use_opus]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_truehd_atmos" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_dtsx" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_opus" in line for line in report.lines)


def test_prepare_import_payload_accepts_aspect_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "aspect",
                            "template_variables": {
                                "use_1.33": False,
                                "use_1.65": False,
                                "use_1.66": False,
                                "use_1.78": False,
                                "use_1.85": False,
                                "use_2.2": False,
                                "use_2.35": False,
                                "use_2.77": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_aspect"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_1.33]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_1.65]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_1.66]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_1.78]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_1.85]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_2.2]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_2.35]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_aspect[use_2.77]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_1.33" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_1.78" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_2.77" in line for line in report.lines)


def test_prepare_import_payload_accepts_video_format_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "video_format",
                            "template_variables": {
                                "use_remux": False,
                                "use_bluray": False,
                                "use_web": False,
                                "use_hdtv": False,
                                "use_dvd": False,
                                "use_sdtv": False,
                                "use_telesync": False,
                                "use_cam": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_video_format"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_remux]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_bluray]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_web]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_hdtv]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_dvd]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_sdtv]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_telesync]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_video_format[use_cam]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_remux" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_hdtv" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_cam" in line for line in report.lines)


def test_prepare_import_payload_accepts_language_count_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "language_count",
                            "template_variables": {
                                "use_dual": False,
                                "use_multi": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_language_count"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_language_count[use_dual]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_language_count[use_multi]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_dual" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_multi" in line for line in report.lines)


def test_prepare_import_payload_accepts_languages_audio_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "languages",
                            "template_variables": {
                                "use_en": False,
                                "use_ja": False,
                                "use_fil": False,
                                "use_myn": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_languages"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages[use_en]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages[use_ja]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages[use_fil]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages[use_myn]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_en" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_fil" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_myn" in line for line in report.lines)


def test_prepare_import_payload_accepts_languages_subtitles_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "languages",
                            "template_variables": {
                                "use_subtitles": True,
                                "use_en": False,
                                "use_ja": False,
                                "use_fil": False,
                                "use_myn": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_languages_subtitles"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages_subtitles[use_en]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages_subtitles[use_ja]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages_subtitles[use_fil]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages_subtitles[use_myn]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_subtitles" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_en" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_myn" in line for line in report.lines)


def test_prepare_import_payload_accepts_status_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Shows": {
                    "overlay_files": [
                        {
                            "default": "status",
                            "template_variables": {
                                "use_airing": False,
                                "use_returning": False,
                                "use_canceled": False,
                                "use_ended": False,
                            },
                        }
                    ]
                }
            }
        },
        set(),
        {"Shows"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["sho-library_shows-show-overlay_status"] is True
    assert libraries_payload["sho-library_shows-show-template_overlay_status[use_airing]"] is False
    assert libraries_payload["sho-library_shows-show-template_overlay_status[use_returning]"] is False
    assert libraries_payload["sho-library_shows-show-template_overlay_status[use_canceled]"] is False
    assert libraries_payload["sho-library_shows-show-template_overlay_status[use_ended]"] is False
    assert any("libraries.Shows.overlay_files[0].template_variables.use_airing" in line for line in report.lines)
    assert any("libraries.Shows.overlay_files[0].template_variables.use_returning" in line for line in report.lines)
    assert any("libraries.Shows.overlay_files[0].template_variables.use_ended" in line for line in report.lines)


def test_prepare_import_payload_accepts_status_alignment_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Shows": {
                    "overlay_files": [
                        {
                            "default": "status",
                            "template_variables": {
                                "horizontal_align": "center",
                                "vertical_align": "bottom",
                            },
                        }
                    ]
                }
            }
        },
        set(),
        {"Shows"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["sho-library_shows-show-overlay_status"] is True
    assert libraries_payload["sho-library_shows-show-template_overlay_status[horizontal_align]"] == "center"
    assert libraries_payload["sho-library_shows-show-template_overlay_status[vertical_align]"] == "bottom"
    assert any("libraries.Shows.overlay_files[0].template_variables.horizontal_align" in line for line in report.lines)
    assert any("libraries.Shows.overlay_files[0].template_variables.vertical_align" in line for line in report.lines)


def test_prepare_import_payload_accepts_streaming_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "streaming",
                            "template_variables": {
                                "use_netflix": False,
                                "use_amazon": False,
                                "use_disney": False,
                                "use_hbomax": False,
                                "use_crunchyroll": False,
                                "use_movistar": False,
                                "use_atresplayer": False,
                                "use_youtube": False,
                                "use_hulu": False,
                                "use_paramount": False,
                                "use_amc": False,
                                "use_appletv": False,
                                "use_peacock": False,
                                "use_discovery": False,
                                "use_crave": False,
                                "use_now": False,
                                "use_channel4": False,
                                "use_itvx": False,
                                "use_bet": False,
                                "use_hayu": False,
                                "use_tubi": False,
                                "use_filmin": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_streaming"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_netflix]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_amazon]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_disney]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_hbomax]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_crunchyroll]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_movistar]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_atresplayer]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_youtube]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_hulu]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_paramount]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_amc]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_appletv]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_peacock]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_discovery]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_crave]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_now]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_channel4]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_itvx]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_bet]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_hayu]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_tubi]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_streaming[use_filmin]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_netflix" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_paramount" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_filmin" in line for line in report.lines)


def test_prepare_import_payload_accepts_ribbon_use_key_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "ribbon",
                            "template_variables": {
                                "use_oscars": False,
                                "use_oscars_director": False,
                                "use_golden": False,
                                "use_golden_director": False,
                                "use_bafta": False,
                                "use_cannes": False,
                                "use_berlinale": False,
                                "use_venice": False,
                                "use_sundance": False,
                                "use_emmys": False,
                                "use_choice": False,
                                "use_spirit": False,
                                "use_cesar": False,
                                "use_imdb": False,
                                "use_letterboxd": False,
                                "use_rottenverified": False,
                                "use_rotten": False,
                                "use_metacritic": False,
                                "use_common": False,
                                "use_razzie": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_ribbon"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_oscars]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_oscars_director]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_golden]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_golden_director]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_bafta]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_cannes]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_berlinale]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_venice]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_sundance]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_emmys]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_choice]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_spirit]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_cesar]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_imdb]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_letterboxd]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_rottenverified]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_rotten]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_metacritic]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_common]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_ribbon[use_razzie]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_oscars" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_imdb" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_razzie" in line for line in report.lines)
