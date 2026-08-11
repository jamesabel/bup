from bup import BupBase, UITypes


class _NoOpBackup(BupBase):
    def run(self):
        self.stop_requested_seen_in_run = self.stop_requested


def _make_backup() -> _NoOpBackup:
    return _NoOpBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)


def test_start_resets_stop_request():
    # a stop request from a prior run must not carry over and silently disable the next run
    backup = _make_backup()
    backup.request_stop()
    assert backup.stop_requested

    backup.start()
    assert backup.wait(10000)

    assert backup.stop_requested_seen_in_run is False
    assert backup.stop_requested is False


def test_start_resets_error_count():
    errors = []
    backup = _make_backup()
    backup.caller_error_out = errors.append
    backup.error_out("boom")
    assert backup.error_count == 1

    backup.start()
    assert backup.wait(10000)

    assert backup.error_count == 0


def test_error_out_increments_error_count():
    errors = []
    backup = _make_backup()
    backup.caller_error_out = errors.append
    backup.error_out("first")
    backup.error_out("second")
    assert backup.error_count == 2
    assert errors == ["first", "second"]
