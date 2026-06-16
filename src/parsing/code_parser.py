"""Parses source code into functions/imports/line counts using tree-sitter."""
from dataclasses import dataclass, field

import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tsts.language_typescript())
JAVA_LANGUAGE = Language(tsjava.language())
GO_LANGUAGE = Language(tsgo.language())

_PARSERS = {
    "python": Parser(PY_LANGUAGE),
    "javascript": Parser(JS_LANGUAGE),
    "typescript": Parser(TS_LANGUAGE),
    "java": Parser(JAVA_LANGUAGE),
    "go": Parser(GO_LANGUAGE),
}

# Each language names its function/method AST nodes differently.
_FUNCTION_NODE_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {
        "function_declaration", "method_definition", "arrow_function", "method_signature"
    },
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
}

_IMPORT_NODE_TYPES = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "java": {"import_declaration"},
    "go": {"import_declaration"},
}


@dataclass
class ParsedFunction:
    name: str
    start_line: int
    end_line: int
    source: str


@dataclass
class ParsedFile:
    language: str
    loc: int
    functions: list[ParsedFunction] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


def _get_parser(language: str) -> Parser:
    parser = _PARSERS.get(language)
    if not parser:
        raise ValueError(f"Unsupported language: {language!r}. Supported: {list(_PARSERS)}")
    return parser


def _node_text(node, code_bytes: bytes) -> str:
    return code_bytes[node.start_byte:node.end_byte].decode("utf-8")


def _function_name(node, code_bytes: bytes) -> str:
    for child in node.children:
        if child.type in ("identifier", "property_identifier", "field_identifier"):
            return _node_text(child, code_bytes)
    return "<anonymous>"


def parse_file(code: str, language: str) -> ParsedFile:
    """language must be one of: python, javascript, typescript, java, go."""
    if language not in _FUNCTION_NODE_TYPES:
        raise ValueError(f"Unsupported language: {language!r}")

    parser = _get_parser(language)
    code_bytes = code.encode("utf-8")
    tree = parser.parse(code_bytes)
    root = tree.root_node

    functions: list[ParsedFunction] = []
    imports: list[str] = []

    def walk(node):
        if node.type in _FUNCTION_NODE_TYPES[language]:
            functions.append(
                ParsedFunction(
                    name=_function_name(node, code_bytes),
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    source=_node_text(node, code_bytes),
                )
            )
        if node.type in _IMPORT_NODE_TYPES.get(language, set()):
            imports.append(_node_text(node, code_bytes).strip())
        for child in node.children:
            walk(child)

    walk(root)

    return ParsedFile(
        language=language,
        loc=len(code.splitlines()),
        functions=functions,
        imports=imports,
    )
