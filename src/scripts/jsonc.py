"""JSON com comentários (JSONC, o formato dos settings do VS Code).

Além de ler (loads), permite edições pontuais — trocar/inserir/remover uma
chave ou item — que mexem só no trecho afetado do texto, preservando
comentários e formatação do resto do arquivo do usuário.
"""

import json
import re
from dataclasses import dataclass, field


class JSONCError(ValueError):
    """Texto não é um JSONC válido."""


_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:[^"\\\n]|\\.)*")
  | (?P<punct>[{}\[\]:,])
  | (?P<literal>[^\s{}\[\]:,"/]+)
    """,
    re.VERBOSE | re.DOTALL,
)


def _tokenize(text: str) -> list[tuple[str, int, int]]:
    """(tipo, início, fim) de cada token, sem espaços nem comentários."""
    tokens = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise JSONCError(f"caractere inesperado na posição {pos}")
        kind = m.lastgroup
        if kind == "punct":
            kind = m.group()
        if kind not in ("ws", "comment"):
            tokens.append((kind, m.start(), m.end()))
        pos = m.end()
    return tokens


@dataclass
class Node:
    kind: str  # "object" | "array" | "scalar"
    start: int
    end: int
    elements: list["Element"] = field(default_factory=list)


@dataclass
class Element:
    key: str | None  # None para itens de array
    start: int  # início da chave (objeto) ou do valor (array)
    value: Node
    comma: int | None  # posição da vírgula logo depois, se houver


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokenize(text)
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i][0] if self.i < len(self.tokens) else None

    def take(self, kind: str | None = None) -> tuple[str, int, int]:
        if self.i >= len(self.tokens):
            raise JSONCError("fim inesperado do arquivo")
        tok = self.tokens[self.i]
        if kind and tok[0] != kind:
            raise JSONCError(f"esperava {kind!r} na posição {tok[1]}, achei {tok[0]!r}")
        self.i += 1
        return tok

    def value(self) -> Node:
        kind = self.peek()
        if kind in ("{", "["):
            return self.container()
        if kind in ("string", "literal"):
            _, start, end = self.take()
            return Node("scalar", start, end)
        raise JSONCError(f"valor esperado, achei {kind!r}")

    def container(self) -> Node:
        open_kind, start, _ = self.take()
        close = "}" if open_kind == "{" else "]"
        node = Node("object" if open_kind == "{" else "array", start, -1)
        while self.peek() != close:
            if open_kind == "{":
                _, key_start, key_end = self.take("string")
                key = json.loads(self.text[key_start:key_end])
                self.take(":")
                el = Element(key, key_start, self.value(), None)
            else:
                val = self.value()
                el = Element(None, val.start, val, None)
            node.elements.append(el)
            if self.peek() == ",":
                el.comma = self.take()[1]
            elif self.peek() != close:
                raise JSONCError(f"esperava ',' ou {close!r}")
        node.end = self.take(close)[2]
        return node


def parse(text: str) -> Node:
    parser = _Parser(text)
    root = parser.value()
    if parser.peek() is not None:
        raise JSONCError("conteúdo extra depois do valor raiz")
    return root


def loads(text: str):
    """Como json.loads, mas aceitando comentários e vírgulas finais."""
    tokens = _tokenize(text)
    parse(text)  # valida a estrutura (mensagem de erro mais clara)
    parts = []
    for n, (kind, start, end) in enumerate(tokens):
        nxt = tokens[n + 1][0] if n + 1 < len(tokens) else None
        if kind == "," and nxt in ("}", "]"):
            continue
        parts.append(text[start:end])
    return json.loads(" ".join(parts))


def find(node: Node, key: str) -> Element | None:
    return next((el for el in node.elements if el.key == key), None)


def _line_start(text: str, pos: int, floor: int) -> int:
    """Início da linha de `pos`, sem recuar antes de `floor`."""
    nl = text.rfind("\n", floor, pos)
    return nl + 1 if nl != -1 else floor


def leading(text: str, container: Node, index: int) -> str:
    """Comentários/linhas em branco que antecedem o elemento `index` (a
    documentação dele), da linha seguinte ao separador anterior até o início
    da linha do próprio elemento (sem a indentação dele)."""
    el = container.elements[index]
    sep = container.elements[index - 1].comma + 1 if index else container.start + 1
    nl = text.find("\n", sep, el.start)
    if nl == -1:
        return ""
    return text[nl + 1 : _line_start(text, el.start, nl + 1)]


def indent_of(text: str, pos: int) -> str:
    """Indentação da linha onde está `pos`."""
    start = _line_start(text, pos, 0)
    return re.match(r"[ \t]*", text[start:]).group()


def replace_value(text: str, el: Element, new_value: str) -> str:
    return text[: el.value.start] + new_value + text[el.value.end :]


def insert_last(text: str, container: Node, element_text: str) -> str:
    """Insere `element_text` (com indentação/comentários próprios, sem quebra
    de linha inicial) como último elemento do objeto/array."""
    if not container.elements:
        pos = container.start + 1
        close_line = _line_start(text, container.end - 1, pos)
        indent = text[close_line : container.end - 1]
        return text[:pos] + "\n" + element_text + "\n" + indent + text[pos:]

    last = container.elements[-1]

    # Container numa linha só (ex: ["a", "b"]): continua numa linha só.
    if "\n" not in text[container.start : container.end]:
        pos = last.comma + 1 if last.comma is not None else last.value.end
        sep = " " if last.comma is not None else ", "
        return text[:pos] + sep + element_text.strip() + text[pos:]

    if last.comma is not None:
        pos = last.comma + 1
        return text[:pos] + "\n" + element_text + text[pos:]
    pos = last.value.end
    return text[:pos] + ",\n" + element_text + text[pos:]


def remove(text: str, container: Node, index: int) -> str:
    """Remove o elemento `index` junto com os comentários que o antecedem e a
    vírgula correspondente, sem deixar vírgula sobrando."""
    el = container.elements[index]
    sep = container.elements[index - 1].comma + 1 if index else container.start + 1

    # Começa na linha seguinte ao separador anterior: um comentário na mesma
    # linha do elemento anterior pertence a ele, não a este.
    nl = text.find("\n", sep, el.start)
    start = nl + 1 if nl != -1 else sep

    end = el.comma + 1 if el.comma is not None else el.value.end
    # Leva junto o resto da linha se for só espaço/comentário.
    eol = text.find("\n", end)
    if eol != -1 and re.fullmatch(r"\s*(//.*)?", text[end:eol]):
        end = eol + 1 if nl != -1 else eol

    prev_comma = None
    if el.comma is None and index:
        prev_comma = container.elements[index - 1].comma

    text = text[:start] + text[end:]
    if prev_comma is not None:
        text = text[:prev_comma] + text[prev_comma + 1 :]
    return text


def set_member(text: str, key: str, value_text: str, doc: str = "") -> str:
    """Troca o valor de `key` no objeto raiz, ou acrescenta a chave no fim
    (precedida de `doc`, ex: o comentário que a explica) se ela não existir."""
    root = parse(text)
    el = find(root, key)
    if el is not None:
        return replace_value(text, el, value_text)
    return insert_last(text, root, f"{doc}    {json.dumps(key)}: {value_text}")


def remove_member(text: str, key: str) -> str:
    root = parse(text)
    for n, el in enumerate(root.elements):
        if el.key == key:
            return remove(text, root, n)
    return text
