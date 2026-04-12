import os
import sys
import threading
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@pytest.fixture(autouse=True)
def reset_job(monkeypatch, tmp_path):
    """Reset global job state and redirect checkpoint dir before each test."""
    import job_manager
    import checkpoint

    monkeypatch.setattr(checkpoint, 'CHECKPOINT_DIR', str(tmp_path))
    monkeypatch.setattr(checkpoint, 'STATE_FILE', str(tmp_path / 'job_state.json'))
    monkeypatch.setattr(checkpoint, 'RESULTS_FILE', str(tmp_path / 'partial_results.csv'))

    job_manager._reset_for_testing()
    yield
    job_manager._reset_for_testing()


def test_get_state_initial():
    import job_manager
    state = job_manager.get_state()
    assert state['status'] == 'idle'


def test_start_transitions_to_running(monkeypatch, tmp_path):
    import job_manager
    import runner

    csv_bytes = b'txClass,status,txHash,toAddress,cryptoCode\n'

    def fake_pipeline(*args, skip_hashes=None, skip_addresses=None, stop_event=None, **kwargs):
        yield {'type': 'status', 'message': 'starting'}
        for i in range(10):
            if stop_event is not None and stop_event.is_set():
                yield {'type': 'stopped'}
                return
            time.sleep(0.05)
            yield {'type': 'progress', 'current': i + 1, 'total': 10, 'hash': f'0x{i:040x}'}
            yield {'type': 'result', 'row': {'hash': f'0x{i:040x}', 'fee_usd': '1.0', 'error': ''}}
        yield {'type': 'done', 'rows': [], 'new': 10, 'failed': 0, 'skipped': 0}

    monkeypatch.setattr(runner, 'run_pipeline', fake_pipeline)

    job_manager.start(csv_bytes, etherscan_key=None)
    time.sleep(0.05)
    state = job_manager.get_state()
    assert state['status'] == 'running'


def test_stop_transitions_to_stopped(monkeypatch, tmp_path):
    import job_manager
    import runner

    csv_bytes = b'txClass,status,txHash,toAddress,cryptoCode\n'

    def fake_pipeline(*args, skip_hashes=None, skip_addresses=None, stop_event=None, **kwargs):
        yield {'type': 'status', 'message': 'starting'}
        for i in range(20):
            if stop_event is not None and stop_event.is_set():
                yield {'type': 'stopped'}
                return
            time.sleep(0.02)
            yield {'type': 'progress', 'current': i + 1, 'total': 20, 'hash': f'0x{i}'}
            yield {'type': 'result', 'row': {'hash': f'0x{i}', 'fee_usd': '1', 'error': ''}}
        yield {'type': 'done', 'rows': [], 'new': 20, 'failed': 0, 'skipped': 0}

    monkeypatch.setattr(runner, 'run_pipeline', fake_pipeline)

    job_manager.start(csv_bytes, etherscan_key=None)
    time.sleep(0.1)
    job_manager.stop()
    time.sleep(0.2)

    state = job_manager.get_state()
    assert state['status'] == 'stopped'


def test_auto_resume_returns_false_when_no_checkpoint():
    import job_manager
    assert job_manager.auto_resume_if_checkpoint() is False


def test_auto_resume_starts_thread_when_checkpoint_exists(monkeypatch, tmp_path):
    import job_manager
    import runner
    import checkpoint

    # Write a fake checkpoint pointing to a real temp CSV
    csv_path = str(tmp_path / 'test.csv')
    with open(csv_path, 'w') as f:
        f.write('txClass,status,txHash,toAddress,cryptoCode\n')

    checkpoint.save(csv_path, 'fakehash', ['0xDONE'], [], '2026-04-12T10:00:00')

    def fake_pipeline(*args, skip_hashes=None, skip_addresses=None, stop_event=None, **kwargs):
        yield {'type': 'status', 'message': 'resuming'}
        yield {'type': 'done', 'rows': [], 'new': 0, 'failed': 0, 'skipped': 0}

    monkeypatch.setattr(runner, 'run_pipeline', fake_pipeline)

    result = job_manager.auto_resume_if_checkpoint()
    assert result is True
    time.sleep(0.1)
    state = job_manager.get_state()
    assert state['status'] in ('running', 'done')
