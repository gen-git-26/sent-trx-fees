import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from runner import validate_csv_columns, MissingColumnsError

def test_validate_csv_columns_passes_with_all_required(tmp_path):
    f = tmp_path / "ok.csv"
    f.write_text("txClass,status,txHash,toAddress,cryptoCode\n")
    validate_csv_columns(str(f))  # should not raise

def test_validate_csv_columns_raises_on_missing(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("txClass,status\n")
    with pytest.raises(MissingColumnsError) as exc_info:
        validate_csv_columns(str(f))
    assert "txHash" in str(exc_info.value)
    assert "toAddress" in str(exc_info.value)
    assert "cryptoCode" in str(exc_info.value)

def test_validate_csv_columns_raises_on_empty_file(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    with pytest.raises(MissingColumnsError):
        validate_csv_columns(str(f))


import threading
import io
import csv

def _make_csv(tmp_path, rows):
    """Helper: write a minimal valid CSV and return its path."""
    p = tmp_path / 'input.csv'
    fieldnames = ['txClass', 'status', 'txHash', 'toAddress', 'cryptoCode']
    with open(p, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(p)


def test_run_pipeline_skip_hashes_skips_entry(tmp_path, monkeypatch):
    """When skip_hashes contains a hash, that hash is not processed."""
    import runner

    processed = []

    def fake_process_transaction(tx_hash, *args, **kwargs):
        processed.append(tx_hash)
        return {'hash': tx_hash, 'error': None}

    monkeypatch.setattr(runner, 'process_transaction', fake_process_transaction)
    monkeypatch.setattr(runner, 'normalize_cashin_row', lambda r: r)
    monkeypatch.setattr(runner, 'preload_all_rates', lambda: {})
    monkeypatch.setattr(runner, 'read_and_filter_merchant_csv',
                        lambda p: (['0xAAA', '0xBBB'], []))

    updates = list(runner.run_pipeline(
        'dummy.csv',
        skip_hashes={'0xAAA'},
    ))

    assert '0xAAA' not in processed
    assert '0xBBB' in processed


def test_run_pipeline_stop_event_halts_pipeline(tmp_path, monkeypatch):
    """When stop_event is set, pipeline yields {'type': 'stopped'} and returns."""
    import runner

    stop_event = threading.Event()
    stop_event.set()  # already set before pipeline runs

    monkeypatch.setattr(runner, 'preload_all_rates', lambda: {})
    monkeypatch.setattr(runner, 'read_and_filter_merchant_csv',
                        lambda p: (['0xAAA', '0xBBB', '0xCCC'], []))
    monkeypatch.setattr(runner, 'process_transaction', lambda *a, **k: {'hash': '0x', 'error': None})
    monkeypatch.setattr(runner, 'normalize_cashin_row', lambda r: r)

    updates = list(runner.run_pipeline('dummy.csv', stop_event=stop_event))
    types = [u['type'] for u in updates]
    assert 'stopped' in types
    assert 'done' not in types
