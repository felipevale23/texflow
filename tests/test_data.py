import json

import pytest

from classes.data import Data


def test_load_from_string_sets_payload():
    d = Data()
    d.load_from_string('{"payload": {"a": 1}}')
    assert d.get_payload() == {"a": 1}


def test_load_from_file(tmp_path):
    file_path = tmp_path / "input.json"
    file_path.write_text(json.dumps({"payload": {"x": 42}}), encoding="utf-8")

    d = Data()
    d.load_from_file(file_path)
    assert d.get_payload() == {"x": 42}


def test_load_from_string_invalid_json_raises_value_error():
    d = Data()
    with pytest.raises(ValueError):
        d.load_from_string("not json")


def test_load_from_string_non_object_raises_type_error():
    d = Data()
    with pytest.raises(TypeError):
        d.load_from_string("[1, 2, 3]")


def test_load_from_string_missing_payload_raises_value_error():
    d = Data()
    with pytest.raises(ValueError):
        d.load_from_string("{}")


def test_load_from_string_payload_not_object_raises_type_error():
    d = Data()
    with pytest.raises(TypeError):
        d.load_from_string('{"payload": [1, 2]}')


def test_get_payload_before_load_raises_runtime_error():
    d = Data()
    with pytest.raises(RuntimeError):
        d.get_payload()
