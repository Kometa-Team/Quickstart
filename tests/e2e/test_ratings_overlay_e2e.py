import pytest


def _ratings_context(page):
    return page.evaluate(
        """() => {
          const group = document.querySelector('.template-toggle-group[data-overlay-id="overlay_ratings"]');
          if (!group) return null;
          const templateName = group.dataset.overlayTemplate || null;
          if (!templateName) return null;
          return { templateName };
        }"""
    )


def _ensure_ratings_harness(page):
    return page.evaluate(
        """() => {
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
        }"""
    )


def _load_library_with_ratings(page):
    library_ids = page.evaluate(
        """() => Array.from(document.querySelectorAll('#libraryPicker option[value]'))
          .map(opt => opt.value)
          .filter(Boolean)"""
    )
    for library_id in library_ids:
        page.select_option("#libraryPicker", library_id)
        page.wait_for_function(
            """(libraryId) => {
              const card = document.querySelector('#library-form-container .library-settings-card');
              return !!card && card.dataset.libraryId === libraryId;
            }""",
            library_id,
            timeout=10000,
        )
        page.wait_for_timeout(300)
        ctx = _ratings_context(page)
        if ctx:
            return ctx
    template_name = _ensure_ratings_harness(page)
    return {"templateName": template_name}


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


def _configure_rating_slots(page, template, enabled):
    slot_values = {
        "rating1": ("user", "rt_tomato"),
        "rating2": ("critic", "imdb"),
        "rating3": ("audience", "tmdb"),
    }
    for slot, (rating_value, image_value) in slot_values.items():
        use_slot = slot in enabled
        _set_by_name(page, f"{template}[{slot}]", rating_value if use_slot else "")
        _set_by_name(page, f"{template}[{slot}_image]", image_value if use_slot else "")


def _slot_offsets(page, template):
    return {
        "rating1": {
            "h": _get_number_value(page, f"{template}[rating1_horizontal_offset]"),
            "v": _get_number_value(page, f"{template}[rating1_vertical_offset]"),
        },
        "rating2": {
            "h": _get_number_value(page, f"{template}[rating2_horizontal_offset]"),
            "v": _get_number_value(page, f"{template}[rating2_vertical_offset]"),
        },
        "rating3": {
            "h": _get_number_value(page, f"{template}[rating3_horizontal_offset]"),
            "v": _get_number_value(page, f"{template}[rating3_vertical_offset]"),
        },
    }


@pytest.mark.e2e
def test_ratings_position_changes_reset_shared_offsets(page, live_server):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    ctx = _load_library_with_ratings(page)
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

                expected_h = 0 if hp == "center" else (-15 if hp == "right" else 15)
                expected_v = 0 if vp == "center" else (-15 if vp == "bottom" else 15)
                got_h = _get_number_value(page, h_name)
                got_v = _get_number_value(page, v_name)
                assert got_h == expected_h, (
                    f"horizontal_offset mismatch for {alignment}/{hp}/{vp}: "
                    f"expected {expected_h}, got {got_h}"
                )
                assert got_v == expected_v, (
                    f"vertical_offset mismatch for {alignment}/{hp}/{vp}: "
                    f"expected {expected_v}, got {got_v}"
                )


@pytest.mark.e2e
@pytest.mark.parametrize(
    "enabled_slots",
    [
        ("rating1", "rating2", "rating3"),
        ("rating1", "rating3"),
        ("rating2",),
    ],
)
def test_ratings_slot_order_across_position_combos(page, live_server, enabled_slots):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    ctx = _load_library_with_ratings(page)
    assert ctx, "Ratings overlay group not found"
    template = ctx["templateName"]
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

                assert axis_values == sorted(axis_values), (
                    f"Slot order mismatch for alignment={alignment}, hp={hp}, vp={vp}, "
                    f"enabled={enabled}: values={axis_values}"
                )

                if enabled_slots == ("rating2",):
                    single = offsets["rating2"]
                    # Single active slot follows shared edge inset behavior (15px), not multi-slot spread.
                    expected_h = 0 if hp == "center" else (-15 if hp == "right" else 15)
                    expected_v = 0 if vp == "center" else (-15 if vp == "bottom" else 15)
                    if alignment == "horizontal":
                        assert single["h"] == expected_h
                        assert single["v"] == expected_v
                    else:
                        assert single["h"] == expected_h
                        assert single["v"] == expected_v
