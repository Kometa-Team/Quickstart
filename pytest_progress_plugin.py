from __future__ import annotations

from _pytest.terminal import TerminalReporter


def _qs_progress_message(self: TerminalReporter) -> str:
    assert self._session
    collected = self._session.testscollected
    if self._show_progress_info == "count":
        if collected:
            progress = self.reported_progress
            counter_format = f"{{:{len(str(collected))}d}}"
            pct = progress * 100 // collected
            return f" [{counter_format}/{collected} {pct:3d}%]".format(progress)
        return " [0/0 100%]"
    return TerminalReporter._qs_original_get_progress_information_message(self)


def _qs_write_progress_information_if_past_edge(self: TerminalReporter) -> None:
    w = self._width_of_current_line
    msg = self._get_progress_information_message()
    past_edge = w + len(msg) + 1 >= self._screen_width
    if past_edge:
        main_color, _ = self._get_main_color()
        self._tw.write(msg + "\n", **{main_color: True})


def pytest_configure(config):
    if getattr(TerminalReporter, "_qs_progress_patch_applied", False):
        return

    TerminalReporter._qs_original_get_progress_information_message = TerminalReporter._get_progress_information_message
    TerminalReporter._qs_original_write_progress_information_if_past_edge = TerminalReporter._write_progress_information_if_past_edge
    TerminalReporter._get_progress_information_message = _qs_progress_message
    TerminalReporter._write_progress_information_if_past_edge = _qs_write_progress_information_if_past_edge
    TerminalReporter._qs_progress_patch_applied = True
