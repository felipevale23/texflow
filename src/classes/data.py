import json
from pathlib import Path
from typing import TypedDict, Any

DATA_DIR = Path("assets/data")

class IData(TypedDict):
    payload: dict[str, Any]

class Data:
    def __init__(self) -> None:
        self._data: IData | None = None

    def load_from_file(self, file_path: Path) -> None:
        try:
            with open(file_path, encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError:
            raise ValueError("JSON inválido")

        self._validate(raw)
        self._data = raw

    def load_from_string(self, json_string: str) -> None:
        try:
            raw = json.loads(json_string)
        except json.JSONDecodeError:
            raise ValueError("JSON inválido")

        self._validate(raw)
        self._data = raw

    def _validate(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("JSON deve ser um objeto")

        if "payload" not in data:
            raise ValueError("Campo obrigatório ausente: payload")

        if not isinstance(data["payload"], dict):
            raise ValueError("payload deve ser um objeto")

    def get_payload(self) -> dict[str, Any]:
        if self._data is None:
            raise RuntimeError("Dados não carregados")
        return self._data["payload"]
