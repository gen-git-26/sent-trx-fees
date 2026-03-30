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
