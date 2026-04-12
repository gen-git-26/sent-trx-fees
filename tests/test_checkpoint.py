import csv
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@pytest.fixture(autouse=True)
def patch_checkpoint_dir(tmp_path, monkeypatch):
    import checkpoint
    monkeypatch.setattr(checkpoint, 'CHECKPOINT_DIR', str(tmp_path))
    monkeypatch.setattr(checkpoint, 'STATE_FILE', str(tmp_path / 'job_state.json'))
    monkeypatch.setattr(checkpoint, 'RESULTS_FILE', str(tmp_path / 'partial_results.csv'))
    yield


def test_load_returns_none_when_missing():
    import checkpoint
    assert checkpoint.load() is None


def test_save_and_load_roundtrip():
    import checkpoint
    checkpoint.save(
        csv_path='/tmp/test.csv',
        csv_hash='abc123',
        processed_hashes=['0xaaa'],
        processed_addresses=['0xbbb'],
        started_at='2026-04-12T10:00:00',
    )
    state = checkpoint.load()
    assert state['csv_hash'] == 'abc123'
    assert '0xaaa' in state['processed_hashes']
    assert '0xbbb' in state['processed_addresses']
    assert state['status'] == 'running'


def test_append_result_and_load(tmp_path):
    import checkpoint
    fieldnames = ['hash', 'fee_usd', 'error']
    checkpoint.append_result({'hash': '0x1', 'fee_usd': '0.50', 'error': ''}, fieldnames)
    checkpoint.append_result({'hash': '0x2', 'fee_usd': '1.00', 'error': ''}, fieldnames)
    rows = checkpoint.load_partial_results(fieldnames)
    assert len(rows) == 2
    assert rows[0]['hash'] == '0x1'
    assert rows[1]['fee_usd'] == '1.00'


def test_clear_removes_files():
    import checkpoint
    fieldnames = ['hash', 'fee_usd', 'error']
    checkpoint.save('/tmp/x.csv', 'h', [], [], '2026-04-12T10:00:00')
    checkpoint.append_result({'hash': '0x1', 'fee_usd': '1', 'error': ''}, fieldnames)
    checkpoint.clear()
    assert checkpoint.load() is None
    assert checkpoint.load_partial_results(fieldnames) == []


def test_append_result_creates_header_once(tmp_path):
    import checkpoint
    fieldnames = ['hash', 'fee_usd', 'error']
    for i in range(3):
        checkpoint.append_result({'hash': f'0x{i}', 'fee_usd': str(i), 'error': ''}, fieldnames)
    with open(checkpoint.RESULTS_FILE, encoding='utf-8-sig') as f:
        content = f.read()
    # header should appear exactly once
    assert content.count('hash,fee_usd,error') == 1
