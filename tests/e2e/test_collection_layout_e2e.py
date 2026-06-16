import pytest


@pytest.mark.e2e
def test_collection_child_numeric_labels_do_not_clip(page, live_server):
    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_timeout(500)

    clipped = page.evaluate("""async () => {
          const existing = document.getElementById('qs-collection-label-clip-harness');
          if (existing) existing.remove();

          const labels = [
            { key: 'limit_released', text: 'Newly Released Limit', width: 240 },
            { key: 'list_days_popular', text: 'Plex Popular List Days', width: 240 },
            { key: 'list_size_watched', text: 'Plex Watched List Size', width: 240 },
            { key: 'limit_top_500', text: 'Letterboxd Top 500 Limit', width: 240 },
            { key: 'limit_oscars', text: 'Oscar Best Picture Winners Limit', width: 320 },
            { key: 'limit_rogerebert', text: "Roger Ebert's Great Movies Limit", width: 320 },
            { key: 'limit_sight_sound', text: 'Sight & Sound Greatest Films Limit', width: 320 },
          ];

          const host = document.createElement('div');
          host.id = 'qs-collection-label-clip-harness';
          host.style.padding = '16px';
          host.style.maxWidth = '1400px';
          document.body.appendChild(host);

          labels.forEach(item => {
            const row = document.createElement('div');
            row.className = 'input-group mb-2';
            row.dataset.templateVariableKey = item.key;

            const label = document.createElement('span');
            label.className = 'input-group-text qs-template-variable-label';
            label.style.width = `${item.width}px`;
            label.textContent = item.text;

            const icon = document.createElement('span');
            icon.className = 'text-info ms-2';
            icon.innerHTML = '<i class="bi bi-info-circle-fill"></i>';
            label.appendChild(icon);

            const input = document.createElement('input');
            input.className = 'form-control';
            input.type = 'number';

            row.appendChild(label);
            row.appendChild(input);
            host.appendChild(row);
          });

          const findings = [];
          host.querySelectorAll('[data-template-variable-key]').forEach(row => {
            const key = String(row.dataset.templateVariableKey || '');
            const label = row.querySelector('.input-group-text');
            if (!label) return;

            const clippedX = label.scrollWidth > label.clientWidth + 1;
            const clippedY = label.scrollHeight > label.clientHeight + 1;
            if (!clippedX && !clippedY) return;

            findings.push({
              key,
              text: (label.innerText || '').trim(),
              clientWidth: label.clientWidth,
              scrollWidth: label.scrollWidth,
              clientHeight: label.clientHeight,
              scrollHeight: label.scrollHeight,
            });
          });

          return findings;
        }""")

    assert clipped == []
