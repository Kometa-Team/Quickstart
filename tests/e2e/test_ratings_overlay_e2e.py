import pytest


def _ratings_context(page, library_id=None, builder_level=None):
    return page.evaluate(
        """([libraryId, builderLevel]) => {
          const cards = Array.from(document.querySelectorAll('#library-form-container .library-settings-card'));
          const card = libraryId
            ? cards.find(c => String(c.dataset.libraryId || '') === String(libraryId)) || null
            : null;
          const root = card || document;
          const groups = Array.from(root.querySelectorAll('.template-toggle-group[data-overlay-id="overlay_ratings"]'));
          if (!groups.length) return null;
          const wantedLevel = (builderLevel || '').toString().toLowerCase();
          const pick = groups.find(group => {
            const builder = group.querySelector('[name$="[builder_level]"]');
            if (!wantedLevel) return !builder;
            if (!builder) return false;
            const raw = (builder.value || builder.dataset.default || '').toString().toLowerCase();
            return raw === wantedLevel;
          }) || groups[0];
          const templateName = pick?.dataset?.overlayTemplate || null;
          if (!templateName) return null;
          return { templateName };
        }""",
        [library_id, builder_level],
    )


def _ensure_ratings_harness(page):
    return page.evaluate("""() => {
          const existing = document.querySelector('[data-test-ratings-harness="true"]');
          if (existing) return existing.dataset.templateName || 'test_ratings_overlay';

          const templateName = 'test_ratings_overlay';
          const host = document.createElement('div');
          host.setAttribute('data-test-ratings-harness', 'true');
          host.dataset.templateName = templateName;
          host.style.display = 'none';

          const group = document.createElement('div');
          group.className = 'template-toggle-group';
          group.dataset.overlayId = 'overlay_ratings';
          group.dataset.overlayTemplate = templateName;
          host.appendChild(group);

          const addInput = (name, value = '') => {
            const input = document.createElement('input');
            input.type = 'text';
            input.name = `${templateName}[${name}]`;
            input.value = String(value);
            input.dataset.default = String(value);
            group.appendChild(input);
            return input;
          };

          const addNumber = (name, value) => {
            const input = document.createElement('input');
            input.type = 'number';
            input.name = `${templateName}[${name}]`;
            input.value = String(value);
            input.dataset.default = String(value);
            group.appendChild(input);
            return input;
          };

          const addSelect = (name, value, options) => {
            const select = document.createElement('select');
            select.name = `${templateName}[${name}]`;
            options.forEach(opt => {
              const option = document.createElement('option');
              option.value = opt;
              option.textContent = opt || 'None';
              if (opt === value) option.selected = true;
              select.appendChild(option);
            });
            select.dataset.default = String(value);
            group.appendChild(select);
            return select;
          };

          addNumber('horizontal_offset', 15);
          addNumber('vertical_offset', 0);
          addNumber('back_height', 160);
          addNumber('back_width', 160);
          addNumber('back_padding', 15);
          addSelect('rating_alignment', 'vertical', ['vertical', 'horizontal']);
          addSelect('addon_position', 'top', ['top', 'left']);
          addSelect('builder_level', 'episode', ['show', 'season', 'episode']);
          addSelect('horizontal_position', 'left', ['left', 'center', 'right']);
          addSelect('vertical_position', 'center', ['top', 'center', 'bottom']);

          addSelect('rating1', 'user', ['', 'user', 'critic', 'audience']);
          addSelect('rating1_image', 'rt_tomato', ['', 'rt_tomato', 'imdb', 'tmdb']);
          addNumber('rating1_horizontal_offset', 30);
          addNumber('rating1_vertical_offset', 30);

          addSelect('rating2', 'critic', ['', 'user', 'critic', 'audience']);
          addSelect('rating2_image', 'imdb', ['', 'rt_tomato', 'imdb', 'tmdb']);
          addNumber('rating2_horizontal_offset', 30);
          addNumber('rating2_vertical_offset', 30);

          addSelect('rating3', 'audience', ['', 'user', 'critic', 'audience']);
          addSelect('rating3_image', 'tmdb', ['', 'rt_tomato', 'imdb', 'tmdb']);
          addNumber('rating3_horizontal_offset', 30);
          addNumber('rating3_vertical_offset', 30);

          document.body.appendChild(host);
          if (typeof window.wireRatingsOffsetSync === 'function') {
            window.wireRatingsOffsetSync(host);
          }
          return templateName;
        }""")


def _load_library_with_ratings(page, builder_level=None):
    library_ids = page.evaluate("""() => Array.from(document.querySelectorAll('#libraryPicker option[value]'))
          .map(opt => opt.value)
          .filter(Boolean)""")
    for library_id in library_ids:
        page.select_option("#libraryPicker", library_id)
        page.wait_for_function(
            """(libraryId) => {
              const card = document.querySelector('#library-form-container .library-settings-card');
              return !!card && card.dataset.libraryId === libraryId;
            }""",
            arg=library_id,
            timeout=10000,
        )
        page.wait_for_timeout(300)
        ctx = _ratings_context(page, library_id, builder_level)
        if ctx:
            ctx["libraryId"] = library_id
            return ctx
    active_library_id = page.evaluate("""() => {
          const card = document.querySelector('#library-form-container .library-settings-card');
          return card?.dataset?.libraryId || null;
        }""")
    if active_library_id:
        page.wait_for_timeout(250)
        ctx = _ratings_context(page, active_library_id, builder_level)
        if ctx:
            ctx["libraryId"] = active_library_id
            return ctx
    template_name = _ensure_ratings_harness(page)
    return {"templateName": template_name, "libraryId": None}


def _set_by_name(page, name, value):
    ok = page.evaluate(
        """([name, value]) => {
          const el = document.querySelector(`[data-test-ratings-harness="true"] [name="${name}"]`) ||
            document.querySelector(`[name="${name}"]`);
          if (!el) return false;
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }""",
        [name, value],
    )
    assert ok, f"Missing input/select: {name}"


def _get_number_value(page, name):
    value = page.evaluate(
        """(name) => {
          const el = document.querySelector(`[data-test-ratings-harness="true"] [name="${name}"]`) ||
            document.querySelector(`[name="${name}"]`);
          if (!el) return null;
          return Number(el.value);
        }""",
        name,
    )
    assert value is not None, f"Missing input: {name}"
    return value


def _get_number_or_none(page, name):
    return page.evaluate(
        """(name) => {
          const el = document.querySelector(`[data-test-ratings-harness="true"] [name="${name}"]`) ||
            document.querySelector(`[name="${name}"]`);
          if (!el) return null;
          return Number(el.value);
        }""",
        name,
    )


def _configure_rating_slots(page, template, enabled):
    slot_values = {
        "rating1": ("user", "rt_tomato"),
        "rating2": ("critic", "imdb"),
        "rating3": ("audience", "tmdb"),
    }
    for slot, (rating_value, image_value) in slot_values.items():
        use_slot = slot in enabled
        _set_if_exists(page, f"{template}[{slot}]", rating_value if use_slot else "")
        _set_if_exists(page, f"{template}[{slot}_image]", image_value if use_slot else "")


def _set_if_exists(page, name, value):
    return page.evaluate(
        """([name, value]) => {
          const el = document.querySelector(`[data-test-ratings-harness="true"] [name="${name}"]`) ||
            document.querySelector(`[name="${name}"]`);
          if (!el) return false;
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }""",
        [name, value],
    )


def _enable_overlay_group(page, template):
    return page.evaluate(
        """(template) => {
          const group = document.querySelector(`[data-overlay-template="${template}"]`);
          if (!group) return false;
          const toggle = group.querySelector('.overlay-toggle');
          if (!toggle) return false;
          if (!toggle.checked) {
            toggle.checked = true;
            toggle.dispatchEvent(new Event('change', { bubbles: true }));
          }
          return true;
        }""",
        template,
    )


def _ensure_overlay_test_hooks(page):
    page.evaluate("""() => {
          const handler = typeof OverlayHandler !== 'undefined'
            ? OverlayHandler
            : window.OverlayHandler
          if (!window.__qsOverlayTestHooks &&
              handler &&
              typeof handler.initializeOverlayBoards === 'function') {
            handler.initializeOverlayBoards(document)
          }
        }""")
    page.wait_for_function(
        """() => !!window.__qsOverlayTestHooks &&
          typeof window.__qsOverlayTestHooks.syncRatingSources === 'function'""",
        timeout=10000,
    )


def _ensure_rating_source_harness(page):
    return page.evaluate("""() => {
      const existing = document.querySelector('[data-test-ratings-source-harness="true"]')
      if (existing) {
        return {
          templateName: existing.dataset.templateName,
          libraryId: existing.dataset.libraryId
        }
      }

      const templateName = 'test_ratings_source_overlay'
      const libraryId = 'test_library'
      const host = document.createElement('div')
      host.setAttribute('data-test-ratings-source-harness', 'true')
      host.dataset.templateName = templateName
      host.dataset.libraryId = libraryId
      host.style.display = 'none'

      const container = document.createElement('div')
      container.className = 'template-toggle-group'
      container.dataset.overlayTemplate = templateName
      container.dataset.overlayType = 'show'
      container.dataset.libraryId = libraryId
      host.appendChild(container)

      const addSelect = (name, value, options) => {
        const select = document.createElement('select')
        select.name = `${templateName}[${name}]`
        options.forEach(opt => {
          const option = document.createElement('option')
          option.value = opt
          option.textContent = opt || 'None'
          if (opt === value) option.selected = true
          select.appendChild(option)
        })
        select.dataset.default = String(value)
        container.appendChild(select)
        return select
      }

      const addToggle = (group, value, checked = false) => {
        const input = document.createElement('input')
        input.type = 'checkbox'
        input.className = 'form-check-input'
        input.id = `${libraryId}-attribute_${group}_${value}`
        input.checked = checked
        host.appendChild(input)
        const label = document.createElement('label')
        label.setAttribute('for', input.id)
        label.textContent = value
        host.appendChild(label)
        return input
      }

      addSelect('rating1', 'user', ['', 'user', 'critic', 'audience'])
      addSelect('rating1_image', 'imdb', ['', 'rt_tomato', 'rt_popcorn', 'imdb'])
      addSelect('rating2', 'critic', ['', 'user', 'critic', 'audience'])
      addSelect('rating2_image', 'rt_tomato', ['', 'rt_tomato', 'rt_popcorn', 'imdb'])
      addSelect('rating3', 'audience', ['', 'user', 'critic', 'audience'])
      addSelect('rating3_image', 'rt_popcorn', ['', 'rt_tomato', 'rt_popcorn', 'imdb'])

      addToggle('mass_critic_rating_update', 'plex_tomatoes', true)
      addToggle('mass_critic_rating_update', 'mdb_tomatoes', false)
      addToggle('mass_audience_rating_update', 'plex_tomatoesaudience', true)
      addToggle('mass_audience_rating_update', 'mdb_tomatoesaudience', false)
      addToggle('mass_user_rating_update', 'imdb', true)

      document.body.appendChild(host)
      return { templateName, libraryId }
    }""")


def _rating_toggle_map(page):
    return page.evaluate("""() => {
      return Array.from(document.querySelectorAll('[data-test-ratings-source-harness="true"] input.form-check-input'))
        .reduce((acc, el) => {
          acc[el.id] = !!el.checked
          return acc
        }, {})
    }""")


def _slot_offsets(page, template):
    return {
        "rating1": {
            "h": _get_number_or_none(page, f"{template}[rating1_horizontal_offset]"),
            "v": _get_number_or_none(page, f"{template}[rating1_vertical_offset]"),
        },
        "rating2": {
            "h": _get_number_or_none(page, f"{template}[rating2_horizontal_offset]"),
            "v": _get_number_or_none(page, f"{template}[rating2_vertical_offset]"),
        },
        "rating3": {
            "h": _get_number_or_none(page, f"{template}[rating3_horizontal_offset]"),
            "v": _get_number_or_none(page, f"{template}[rating3_vertical_offset]"),
        },
    }


def _ratings_layer_margins(page, library_id, board_type):
    return page.evaluate(
        """([libraryId, boardType]) => {
          const cards = Array.from(document.querySelectorAll('#library-form-container .library-settings-card'));
          const card = cards.find(c => String(c.dataset.libraryId || '') === String(libraryId));
          if (!card) return null;
          const board = card.querySelector(`.overlay-board[data-overlay-type="${boardType}"]`);
          if (!board) return null;
          const canvas = board.querySelector('.overlay-board-canvas');
          if (!canvas) return null;
          const layer = canvas.querySelector('.overlay-board-layer[data-overlay-type="overlay_ratings"]');
          if (!layer) return null;
          const style = window.getComputedStyle(layer);
          if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return null;

          const baseW = Number(board.dataset.baseWidth || 1000);
          const baseH = Number(board.dataset.baseHeight || 1500);
          const canvasRect = canvas.getBoundingClientRect();
          const layerRect = layer.getBoundingClientRect();
          const scaleX = (canvasRect.width || 1) / baseW;
          const scaleY = (canvasRect.height || 1) / baseH;
          if (!Number.isFinite(scaleX) || !Number.isFinite(scaleY) || scaleX <= 0 || scaleY <= 0) return null;

          return {
            left: (layerRect.left - canvasRect.left) / scaleX,
            right: (canvasRect.right - layerRect.right) / scaleX,
            top: (layerRect.top - canvasRect.top) / scaleY,
            bottom: (canvasRect.bottom - layerRect.bottom) / scaleY
          };
        }""",
        [library_id, board_type],
    )


@pytest.mark.e2e
def test_ratings_position_changes_reset_shared_offsets(page, live_server):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    ctx = _load_library_with_ratings(page, builder_level="show")
    assert ctx, "Ratings overlay group not found"
    template = ctx["templateName"]

    h_name = f"{template}[horizontal_offset]"
    v_name = f"{template}[vertical_offset]"
    a_name = f"{template}[rating_alignment]"
    hp_name = f"{template}[horizontal_position]"
    vp_name = f"{template}[vertical_position]"

    for alignment in ("vertical", "horizontal"):
        for hp in ("left", "center", "right"):
            for vp in ("top", "center", "bottom"):
                _set_by_name(page, h_name, "777")
                _set_by_name(page, v_name, "888")
                _set_by_name(page, a_name, alignment)
                _set_by_name(page, hp_name, hp)
                _set_by_name(page, vp_name, vp)
                page.wait_for_timeout(150)

                expected_h = 0 if hp == "center" else 15
                expected_v = 0 if vp == "center" else 15
                got_h = _get_number_value(page, h_name)
                got_v = _get_number_value(page, v_name)
                assert got_h == expected_h, f"horizontal_offset mismatch for {alignment}/{hp}/{vp}: " f"expected {expected_h}, got {got_h}"
                assert got_v == expected_v, f"vertical_offset mismatch for {alignment}/{hp}/{vp}: " f"expected {expected_v}, got {got_v}"


@pytest.mark.e2e
def test_ratings_shared_nudge_sync_respects_anchor_math(page, live_server):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)
    template = _ensure_ratings_harness(page)

    # Horizontal + left/top: shared +15 should move each slot +15 on each axis.
    _set_by_name(page, f"{template}[rating_alignment]", "horizontal")
    _set_by_name(page, f"{template}[horizontal_position]", "left")
    _set_by_name(page, f"{template}[vertical_position]", "top")
    page.wait_for_timeout(100)
    _set_by_name(page, f"{template}[horizontal_offset]", "30")
    _set_by_name(page, f"{template}[vertical_offset]", "30")
    page.wait_for_timeout(100)

    offsets = _slot_offsets(page, template)
    assert offsets["rating1"]["h"] == 45
    assert offsets["rating2"]["h"] == 360
    assert offsets["rating3"]["h"] == 675
    assert offsets["rating1"]["v"] == 45
    assert offsets["rating2"]["v"] == 45
    assert offsets["rating3"]["v"] == 45

    # Horizontal + right/bottom: shared +15 means move inward from right/bottom.
    _set_by_name(page, f"{template}[horizontal_position]", "right")
    _set_by_name(page, f"{template}[vertical_position]", "bottom")
    page.wait_for_timeout(100)
    _set_by_name(page, f"{template}[horizontal_offset]", "30")
    _set_by_name(page, f"{template}[vertical_offset]", "30")
    page.wait_for_timeout(100)

    offsets = _slot_offsets(page, template)
    assert offsets["rating1"]["h"] == -675
    assert offsets["rating2"]["h"] == -360
    assert offsets["rating3"]["h"] == -45
    assert offsets["rating1"]["v"] == -45
    assert offsets["rating2"]["v"] == -45
    assert offsets["rating3"]["v"] == -45


@pytest.mark.e2e
@pytest.mark.parametrize("builder_level", ["show", "episode"])
def test_ratings_edge_positions_respect_15px_margin(page, live_server, builder_level):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    ctx = _load_library_with_ratings(page, builder_level=builder_level)
    assert ctx, "Ratings overlay group not found"
    template = ctx["templateName"]
    library_id = ctx.get("libraryId")

    _set_if_exists(page, f"{template}[builder_level]", builder_level)
    _enable_overlay_group(page, template)
    _configure_rating_slots(page, template, {"rating1", "rating2", "rating3"})

    combos = [
        ("vertical", "left", "top"),
        ("vertical", "right", "bottom"),
        ("horizontal", "left", "top"),
        ("horizontal", "right", "bottom"),
    ]
    board_type = "episode" if builder_level == "episode" else "show"

    for alignment, hp, vp in combos:
        _set_by_name(page, f"{template}[rating_alignment]", alignment)
        _set_by_name(page, f"{template}[horizontal_position]", hp)
        _set_by_name(page, f"{template}[vertical_position]", vp)
        page.wait_for_timeout(350)

        # If fixture cannot provide a real library card/canvas, still validate
        # edge-anchor defaults via shared offsets to avoid skip-only coverage.
        if not library_id:
            got_h = _get_number_value(page, f"{template}[horizontal_offset]")
            got_v = _get_number_value(page, f"{template}[vertical_offset]")
            expected_h = 0 if hp == "center" else 15
            expected_v = 0 if vp == "center" else 15
            assert got_h == expected_h, f"horizontal_offset mismatch for {builder_level} {alignment}/{hp}/{vp}: " f"expected {expected_h}, got {got_h}"
            assert got_v == expected_v, f"vertical_offset mismatch for {builder_level} {alignment}/{hp}/{vp}: " f"expected {expected_v}, got {got_v}"
            continue

        margins = _ratings_layer_margins(page, library_id, board_type)
        assert margins is not None, f"Ratings layer not available for {builder_level} {alignment}/{hp}/{vp}"

        if hp == "left":
            assert margins["left"] >= 14.0, f"Left margin too small ({margins['left']}) for {alignment}/{hp}/{vp}"
        if hp == "right":
            assert margins["right"] >= 14.0, f"Right margin too small ({margins['right']}) for {alignment}/{hp}/{vp}"
        if vp == "top":
            assert margins["top"] >= 14.0, f"Top margin too small ({margins['top']}) for {alignment}/{hp}/{vp}"
        if vp == "bottom":
            assert margins["bottom"] >= 14.0, f"Bottom margin too small ({margins['bottom']}) for {alignment}/{hp}/{vp}"


@pytest.mark.e2e
@pytest.mark.parametrize(
    "enabled_slots,builder_level",
    [
        (("rating1", "rating2", "rating3"), "show"),
        (("rating1", "rating3"), "show"),
        (("rating1", "rating2"), "episode"),
        (("rating2",), "episode"),
    ],
)
def test_ratings_slot_order_across_position_combos(page, live_server, enabled_slots, builder_level):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    ctx = _load_library_with_ratings(page, builder_level=builder_level)
    assert ctx, "Ratings overlay group not found"
    template = ctx["templateName"]
    _set_if_exists(page, f"{template}[builder_level]", builder_level)
    _configure_rating_slots(page, template, set(enabled_slots))

    for alignment in ("vertical", "horizontal"):
        for hp in ("left", "center", "right"):
            for vp in ("top", "center", "bottom"):
                _set_by_name(page, f"{template}[rating_alignment]", alignment)
                _set_by_name(page, f"{template}[horizontal_position]", hp)
                _set_by_name(page, f"{template}[vertical_position]", vp)
                page.wait_for_timeout(200)

                offsets = _slot_offsets(page, template)
                enabled = [slot for slot in ("rating1", "rating2", "rating3") if slot in enabled_slots]
                if alignment == "horizontal":
                    axis_values = [offsets[slot]["h"] for slot in enabled]
                else:
                    axis_values = [offsets[slot]["v"] for slot in enabled]
                assert all(v is not None for v in axis_values), f"Missing slot offsets for enabled={enabled}, alignment={alignment}, hp={hp}, vp={vp}: {offsets}"

                assert axis_values == sorted(axis_values), f"Slot order mismatch for alignment={alignment}, hp={hp}, vp={vp}, " f"enabled={enabled}: values={axis_values}"

                if enabled_slots == ("rating2",):
                    single = offsets["rating2"]
                    # Single active slot follows slot anchor spacing (30px edge / 0px center).
                    expected_h = 0 if hp == "center" else (-30 if hp == "right" else 30)
                    expected_v = 0 if vp == "center" else (-30 if vp == "bottom" else 30)
                    if alignment == "horizontal":
                        assert single["h"] == expected_h
                        assert single["v"] == expected_v
                    else:
                        assert single["h"] == expected_h
                        assert single["v"] == expected_v


@pytest.mark.e2e
def test_ratings_toggle_preserves_existing_rt_mass_sources(page, live_server):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)
    _ensure_overlay_test_hooks(page)
    ctx = _ensure_rating_source_harness(page)
    library_id = ctx["libraryId"]

    page.evaluate(
        """(libraryId) => {
          const container = document.querySelector('[data-test-ratings-source-harness="true"] [data-overlay-template]')
          const sync = window.__qsOverlayTestHooks.syncRatingSources
          sync({ container }, { ratingKey: 'rating2', imageKey: 'rating2_image' }, { preserveExisting: true })
          sync({ container }, { ratingKey: 'rating3', imageKey: 'rating3_image' }, { preserveExisting: true })
          return {
            critic: window.__qsOverlayTestHooks.getCurrentMassToggleValue(libraryId, 'mass_critic_rating_update'),
            audience: window.__qsOverlayTestHooks.getCurrentMassToggleValue(libraryId, 'mass_audience_rating_update')
          }
        }""",
        library_id,
    )

    checked = _rating_toggle_map(page)
    assert checked[f"{library_id}-attribute_mass_critic_rating_update_plex_tomatoes"] is True
    assert checked.get(f"{library_id}-attribute_mass_critic_rating_update_mdb_tomatoes", False) is False
    assert checked[f"{library_id}-attribute_mass_audience_rating_update_plex_tomatoesaudience"] is True
    assert checked.get(f"{library_id}-attribute_mass_audience_rating_update_mdb_tomatoesaudience", False) is False
    assert checked[f"{library_id}-attribute_mass_user_rating_update_imdb"] is True

    page.evaluate(
        """(libraryId) => {
          const container = document.querySelector('[data-test-ratings-source-harness="true"] [data-overlay-template]')
          document.getElementById(`${libraryId}-attribute_mass_critic_rating_update_plex_tomatoes`).checked = false
          document.getElementById(`${libraryId}-attribute_mass_critic_rating_update_mdb_tomatoes`).checked = false
          document.getElementById(`${libraryId}-attribute_mass_audience_rating_update_plex_tomatoesaudience`).checked = false
          document.getElementById(`${libraryId}-attribute_mass_audience_rating_update_mdb_tomatoesaudience`).checked = false
          const sync = window.__qsOverlayTestHooks.syncRatingSources
          sync({ container }, { ratingKey: 'rating2', imageKey: 'rating2_image' }, { preserveExisting: true })
          sync({ container }, { ratingKey: 'rating3', imageKey: 'rating3_image' }, { preserveExisting: true })
        }""",
        library_id,
    )

    checked = _rating_toggle_map(page)
    assert checked[f"{library_id}-attribute_mass_critic_rating_update_mdb_tomatoes"] is True
    assert checked.get(f"{library_id}-attribute_mass_critic_rating_update_plex_tomatoes", False) is False
    assert checked[f"{library_id}-attribute_mass_audience_rating_update_mdb_tomatoesaudience"] is True
    assert checked.get(f"{library_id}-attribute_mass_audience_rating_update_plex_tomatoesaudience", False) is False
