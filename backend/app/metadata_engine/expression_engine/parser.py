"""Expression parser for reusable metadata expressions."""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Iterable

from app.metadata_engine.expression_engine.ast import (
    BinaryOpNode,
    ExpressionNode,
    FunctionNode,
    IdentifierNode,
    LiteralNode,
    ObjectNode,
    UnaryOpNode,
)


TOKEN_RE = re.compile(
    r"(?P<NUMBER>\b\d+(?:\.\d+)?\b)|"
    r"(?P<STRING>'[^']*'|\"[^\"]*\")|"
    r"(?P<IDENT>[A-Za-z_][A-Za-z0-9_.]*)|"
    r"(?P<OP>\+|\-|\*|\/|<=|>=|==|!=|<|>|\(|\)|\{|\}|:|,)|"
    r"(?P<WS>\s+)",
)

FUNCTIONS = {"IF", "AND", "OR", "NOT", "CASE", "SUM", "AVG", "COUNT", "MAX", "MIN", "LOOKUP", "TODAY", "NOW", "DATEADD", "DATEDIFF"}


@dataclass(frozen=True)
class Token:
    type: str
    value: str


class ParseError(Exception):
    pass


class ExpressionLexer:
    def __init__(self, expression: str):
        self.expression = expression
        self.tokens = self._tokenize(expression)
        self.index = 0

    def _tokenize(self, expression: str) -> list[Token]:
        tokens: list[Token] = []
        for match in TOKEN_RE.finditer(expression):
            kind = match.lastgroup
            value = match.group(0)
            if kind == "WS":
                continue
            tokens.append(Token(kind, value))
        return tokens

    def peek(self) -> Token | None:
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return None

    def next(self) -> Token | None:
        token = self.peek()
        if token is not None:
            self.index += 1
        return token

    def expect(self, token_type: str, value: str | None = None) -> Token:
        token = self.next()
        if token is None or token.type != token_type or (value is not None and token.value != value):
            raise ParseError(f"Expected {token_type} {value or ''}, got {token}")
        return token


def parse_expression(expression: str) -> ExpressionNode:
    lexer = ExpressionLexer(expression)
    node = parse_or_expression(lexer)
    if lexer.peek() is not None:
        raise ParseError(f"Unexpected token: {lexer.peek()}")
    return node


def parse_or_expression(lexer: ExpressionLexer) -> ExpressionNode:
    node = parse_and_expression(lexer)
    while (token := lexer.peek()) and token.value.upper() == "OR":
        lexer.next()
        right = parse_and_expression(lexer)
        node = BinaryOpNode("OR", node, right)
    return node


def parse_and_expression(lexer: ExpressionLexer) -> ExpressionNode:
    node = parse_not_expression(lexer)
    while (token := lexer.peek()) and token.value.upper() == "AND":
        lexer.next()
        right = parse_not_expression(lexer)
        node = BinaryOpNode("AND", node, right)
    return node


def parse_not_expression(lexer: ExpressionLexer) -> ExpressionNode:
    if (token := lexer.peek()) and token.value.upper() == "NOT":
        lexer.next()
        operand = parse_not_expression(lexer)
        return UnaryOpNode("NOT", operand)
    return parse_comparison(lexer)


def parse_comparison(lexer: ExpressionLexer) -> ExpressionNode:
    node = parse_additive(lexer)
    while (token := lexer.peek()) and token.type == "OP" and token.value in ("==", "!=", "<", ">", "<=", ">="):
        op = token.value
        lexer.next()
        right = parse_additive(lexer)
        node = BinaryOpNode(op, node, right)
    return node


def parse_additive(lexer: ExpressionLexer) -> ExpressionNode:
    node = parse_term(lexer)
    while (token := lexer.peek()) and token.type == "OP" and token.value in ("+", "-"):
        op = token.value
        lexer.next()
        right = parse_term(lexer)
        node = BinaryOpNode(op, node, right)
    return node


def parse_term(lexer: ExpressionLexer) -> ExpressionNode:
    node = parse_factor(lexer)
    while (token := lexer.peek()) and token.type == "OP" and token.value in ("*", "/"):
        op = token.value
        lexer.next()
        right = parse_factor(lexer)
        node = BinaryOpNode(op, node, right)
    return node


def parse_factor(lexer: ExpressionLexer) -> ExpressionNode:
    token = lexer.peek()
    if token is None:
        raise ParseError("Unexpected end of expression")

    if token.type == "NUMBER":
        lexer.next()
        return LiteralNode(float(token.value) if "." in token.value else int(token.value))

    if token.type == "STRING":
        lexer.next()
        return LiteralNode(token.value[1:-1])

    if token.type == "IDENT":
        lexer.next()
        if lexer.peek() and lexer.peek().value == "(":
            return parse_function(lexer, token.value)
        return IdentifierNode(token.value)

    if token.value == "(":
        lexer.next()
        node = parse_or_expression(lexer)
        lexer.expect("OP", ")")
        return node

    if token.value == "{":
        return parse_object(lexer)

    if token.value == "-":
        lexer.next()
        return UnaryOpNode("NEG", parse_factor(lexer))

    raise ParseError(f"Unexpected token: {token}")


def parse_object(lexer: ExpressionLexer) -> ExpressionNode:
    lexer.expect("OP", "{")
    props: dict[str, ExpressionNode] = {}
    while lexer.peek() and lexer.peek().value != "}":
        key_token = lexer.next()
        if key_token is None or key_token.type not in {"STRING", "IDENT"}:
            raise ParseError("Expected string or identifier key in object literal")
        key = key_token.value
        if key_token.type == "STRING":
            key = key[1:-1]
        lexer.expect("OP", ":")
        value = parse_or_expression(lexer)
        props[key] = value
        if lexer.peek() and lexer.peek().value == ",":
            lexer.next()
    lexer.expect("OP", "}")
    return ObjectNode(props)


def parse_function(lexer: ExpressionLexer, name: str) -> FunctionNode:
    lexer.expect("OP", "(")
    args: list[ExpressionNode] = []
    if lexer.peek() and lexer.peek().value != ")":
        args.append(parse_or_expression(lexer))
        while lexer.peek() and lexer.peek().value == ",":
            lexer.next()
            args.append(parse_or_expression(lexer))
    lexer.expect("OP", ")")
    return FunctionNode(name.upper(), tuple(args))
