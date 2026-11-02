import pytest

from scripts import jsonc


def test_loads_accepts_comments_and_trailing_commas():
    text = '{\n  // c\n  "a": "http://x", /* b */\n  "l": [1, 2,],\n}'
    assert jsonc.loads(text) == {"a": "http://x", "l": [1, 2]}


@pytest.mark.parametrize("bad", ["", "{", '{"a" 1}', '{"a": 1} x', "conteúdo qualquer"])
def test_loads_rejects_invalid(bad):
    with pytest.raises(ValueError):
        jsonc.loads(bad)


def test_set_member_replaces_only_the_value():
    text = '{\n    // doc\n    "a": 1, // fica\n    "b": [1]\n}\n'
    out = jsonc.set_member(text, "a", '"novo"')
    assert out == '{\n    // doc\n    "a": "novo", // fica\n    "b": [1]\n}\n'


@pytest.mark.parametrize(
    "text",
    [
        '{\n    "a": 1\n}\n',
        '{\n    "a": 1,\n}\n',
        "{}",
        '{"a": 1}',
    ],
)
def test_set_member_appends_valid_json(text):
    out = jsonc.set_member(text, "novo", "[1, 2]", doc="    // explicação\n")
    data = jsonc.loads(out)
    assert data["novo"] == [1, 2]
    assert ("a" in data) == ("a" in text)


@pytest.mark.parametrize(
    ("text", "key", "expected"),
    [
        ('{\n    "a": 1,\n    // doc b\n    "b": 2,\n    "c": 3\n}\n', "b", '{\n    "a": 1,\n    "c": 3\n}\n'),
        ('{\n    "a": 1, // de a\n    // doc c\n    "c": 3\n}\n', "c", '{\n    "a": 1 // de a\n}\n'),
        ('{\n    // doc a\n    "a": 1,\n    "c": 3\n}\n', "a", '{\n    "c": 3\n}\n'),
        ('{"a": 1, "b": 2}', "b", '{"a": 1}'),
        ('{"a": 1}', "zzz", '{"a": 1}'),
    ],
)
def test_remove_member(text, key, expected):
    out = jsonc.remove_member(text, key)
    assert out == expected
    jsonc.loads(out)
