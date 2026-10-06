import sys


class CompileError(Exception):
    def __init__(self, line, col, msg):
        super().__init__(msg)
        self.line, self.col, self.msg = line, col, msg


class TokenType:
    MODIFIER = "MODIFIER"
    TYPE = "TYPE"
    ID = "ID"
    INT = "INT"
    BOOL_LIT = "BOOL_LIT"
    ASSIGN = "ASSIGN"
    EQ = "EQ"
    NEQ = "NEQ"
    IF = "IF"
    ELSE = "ELSE"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    EXIT = "EXIT"
    NEWLINE = "NEWLINE"
    EOF = "EOF"


class Token:
    def __init__(self, kind, text, line, col):
        self.kind, self.text, self.line, self.col = kind, text, line, col

    def __repr__(self):
        return f"Token({self.kind}, {self.text!r}, {self.line}:{self.col})"


KEYWORDS = [
    ("🚫", TokenType.MODIFIER),            # constant
    ("🙂", TokenType.MODIFIER),            # mutable variable
    ("\u2639\ufe0f", TokenType.MODIFIER),  # ☹️  immutable variable (with variation selector)
    ("🐒", TokenType.TYPE),                # i32
    ("🦍", TokenType.TYPE),                # i64
    ("boo!👻", TokenType.TYPE),            # bool
    ("👍", TokenType.BOOL_LIT),
    ("👎", TokenType.BOOL_LIT),
    ("🤔", TokenType.IF),
    ("🤨", TokenType.ELSE),
    ("🚪", TokenType.EXIT),
    ("✅", TokenType.EQ),
    ("❎", TokenType.NEQ),
    ("=>", TokenType.ASSIGN),
    ("{", TokenType.LBRACE),
    ("}", TokenType.RBRACE),
]

_ACCEPT = "accept"  # key marking an accepting state in the keyword automaton


def _build_automaton(words):
    """Build the keyword state machine: states are dicts, transitions are bytes."""
    root = {}
    for text, kind in words:
        state = root
        for b in text.encode("utf-8"):
            state = state.setdefault(b, {})
        state[_ACCEPT] = kind
    return root


KEYWORD_AUTOMATON = _build_automaton(KEYWORDS)


def is_digit(b):
    return 0x30 <= b <= 0x39


def is_letter(b):  # ASCII letters and '_'
    return 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A or b == 0x5F


class Lexer:
    def __init__(self, data):
        self.data = data  # bytes
        self.pos = 0
        self.line = 1
        self.col = 1  # counted in characters, not bytes

    def peek(self, offset=0):
        i = self.pos + offset
        return self.data[i] if i < len(self.data) else -1

    def advance(self):
        b = self.data[self.pos]
        self.pos += 1
        if b == 0x0A:
            self.line += 1
            self.col = 1
        elif (b & 0xC0) != 0x80:  # UTF-8 continuation bytes do not start a new column
            self.col += 1
        return b

    def error(self, msg, line, col):
        raise CompileError(line, col, msg)

    def next_token(self):
        while self.peek() in (0x20, 0x09):
            self.advance()
        line, col = self.line, self.col
        b = self.peek()

        if b == -1:
            return Token(TokenType.EOF, "", line, col)
        if b == 0x0A:
            self.advance()
            return Token(TokenType.NEWLINE, "\\n", line, col)
        if b == 0x0D:
            if self.peek(1) == 0x0A:
                self.advance()
                self.advance()
                return Token(TokenType.NEWLINE, "\\r\\n", line, col)
            self.error("Unknown character '\\r' (a carriage return must be followed by a line feed)", line, col)

        if is_digit(b):
            start = self.pos
            while is_digit(self.peek()):
                self.advance()
            return Token(TokenType.INT, self.data[start:self.pos].decode("ascii"), line, col)

        state, i = KEYWORD_AUTOMATON, 0
        best_kind, best_len = None, 0
        while True:
            nxt = state.get(self.peek(i))
            if nxt is None:
                break
            state = nxt
            i += 1
            if _ACCEPT in state:
                best_kind, best_len = state[_ACCEPT], i
        if best_kind is not None:
            start = self.pos
            for _ in range(best_len):
                self.advance()
            return Token(best_kind, self.data[start:self.pos].decode("utf-8"), line, col)

        if is_letter(b):
            start = self.pos
            while is_letter(self.peek()) or is_digit(self.peek()):
                self.advance()
            return Token(TokenType.ID, self.data[start:self.pos].decode("ascii"), line, col)

        self.unknown_character(b, line, col)

    def unknown_character(self, b, line, col):
        n = 4 if b >= 0xF0 else 3 if b >= 0xE0 else 2 if b >= 0xC0 else 1
        try:
            ch = self.data[self.pos:self.pos + n].decode("utf-8")
        except UnicodeDecodeError:
            self.error(f"Invalid UTF-8 byte 0x{b:02X}", line, col)
        hint = " (assignment is written '=>')" if ch == "=" else ""
        self.error(f"Unknown character '{ch}'{hint}", line, col)


MODIFIER_NAMES = {"🚫": "constant", "🙂": "mutable", "\u2639\ufe0f": "immutable"}
TYPE_NAMES = {"🐒": "i32", "🦍": "i64", "boo!👻": "bool"}
OP_NAMES = {"✅": "==", "❎": "!="}


class ASTNode:
    """Base class. Every node keeps the position of the token it came from."""

    def __init__(self, line, col):
        self.line, self.col = line, col

    def details(self):
        return ""

    def children(self):
        return []

    def dump(self, depth=0):
        d = self.details()
        head = "  " * depth + f"{type(self).__name__} @{self.line}:{self.col}" + (f" ({d})" if d else "")
        lines = [head]
        for child in self.children():
            lines.extend(child.dump(depth + 1))
        return lines


class ProgramNode(ASTNode):
    def __init__(self, line, col):
        super().__init__(line, col)
        self.statements = []

    def children(self):
        return self.statements


class StmtNode(ASTNode):
    pass


class _DeclMixin:
    def init_decl(self, mod_tok, type_tok, id_tok):
        self.modifier = MODIFIER_NAMES[mod_tok.text]
        self.mutable = self.modifier == "mutable"
        self.type_name = TYPE_NAMES[type_tok.text]
        self.name = id_tok.text

    def decl_details(self):
        return (f"modifier: {self.modifier}, mutable: {str(self.mutable).lower()}, "
                f"type: {self.type_name}, name: {self.name}")


class DeclarationNode(StmtNode, _DeclMixin):
    def __init__(self, mod_tok, type_tok, id_tok):
        super().__init__(mod_tok.line, mod_tok.col)
        self.init_decl(mod_tok, type_tok, id_tok)

    def details(self):
        return self.decl_details()


class DeclAndAssignNode(StmtNode, _DeclMixin):
    def __init__(self, mod_tok, type_tok, id_tok, expr):
        super().__init__(mod_tok.line, mod_tok.col)
        self.init_decl(mod_tok, type_tok, id_tok)
        self.expr = expr

    def details(self):
        return self.decl_details()

    def children(self):
        return [self.expr]


class AssignmentNode(StmtNode):
    def __init__(self, id_tok, expr):
        super().__init__(id_tok.line, id_tok.col)
        self.name = id_tok.text
        self.expr = expr

    def details(self):
        return f"name: {self.name}"

    def children(self):
        return [self.expr]


class IfNode(StmtNode):
    def __init__(self, if_tok, cond, then_stmts, else_stmts):
        super().__init__(if_tok.line, if_tok.col)
        self.cond, self.then_stmts, self.else_stmts = cond, then_stmts, else_stmts  # else_stmts: None if absent

    def dump(self, depth=0):
        pad = "  " * (depth + 1)
        lines = ["  " * depth + f"IfNode @{self.line}:{self.col}", pad + "Condition"]
        lines += self.cond.dump(depth + 2)
        lines.append(pad + "Then")
        for s in self.then_stmts:
            lines += s.dump(depth + 2)
        if self.else_stmts is not None:
            lines.append(pad + "Else")
            for s in self.else_stmts:
                lines += s.dump(depth + 2)
        return lines


class ExitNode(StmtNode):
    def __init__(self, exit_tok, id_tok):
        super().__init__(exit_tok.line, exit_tok.col)
        self.name = id_tok.text

    def details(self):
        return f"name: {self.name}"


class ExprNode(ASTNode):
    pass


class BinOpNode(ExprNode):
    def __init__(self, left, op_tok, right):
        super().__init__(op_tok.line, op_tok.col)
        self.left, self.op, self.right = left, OP_NAMES[op_tok.text], right

    def details(self):
        return f"op: {self.op}"

    def children(self):
        return [self.left, self.right]


class ValueNode(ExprNode):
    def __init__(self, tok):
        super().__init__(tok.line, tok.col)
        self.kind = tok.kind
        if tok.kind == TokenType.BOOL_LIT:
            self.kind_name, self.value = "BOOL", ("true" if tok.text == "👍" else "false")
        else:
            self.kind_name, self.value = tok.kind, tok.text  # "ID" or "INT"

    def details(self):
        return f"{self.kind_name}: {self.value}"


EXPECTED = {
    TokenType.MODIFIER: "a modifier (🚫, 🙂 or ☹️)",
    TokenType.TYPE: "a type (🐒, 🦍 or boo!👻)",
    TokenType.ID: "an identifier",
    TokenType.INT: "an integer literal",
    TokenType.BOOL_LIT: "a boolean literal",
    TokenType.ASSIGN: "'=>'",
    TokenType.EQ: "'✅'",
    TokenType.NEQ: "'❎'",
    TokenType.IF: "'🤔'",
    TokenType.ELSE: "'🤨'",
    TokenType.LBRACE: "'{'",
    TokenType.RBRACE: "'}'",
    TokenType.EXIT: "'🚪'",
    TokenType.NEWLINE: "end of line",
    TokenType.EOF: "end of file",
}


def describe(tok):
    if tok.kind == TokenType.EOF:
        return "end of file"
    if tok.kind == TokenType.NEWLINE:
        return "end of line"
    return f"'{tok.text}'"


class Parser:
    def __init__(self, lexer):
        self.lexer = lexer
        self.cur = lexer.next_token()

    def peek(self):
        return self.cur

    def error_at(self, tok, msg):
        raise CompileError(tok.line, tok.col, msg)

    def eat(self, kind):
        if self.cur.kind == kind:
            tok = self.cur
            self.cur = self.lexer.next_token()
            return tok
        self.error_at(self.cur, f"Expected {EXPECTED[kind]}, got {describe(self.cur)}")

    def parse_program(self):
        first = self.peek()
        node = ProgramNode(first.line, first.col)
        node.statements.append(self.parse_statement())
        while self.peek().kind != TokenType.EOF:
            node.statements.append(self.parse_statement())
        return node

    def parse_statement(self):
        kind = self.peek().kind
        if kind == TokenType.IF:
            return self.parse_if()
        if kind == TokenType.EXIT:
            return self.parse_exit()
        if kind in (TokenType.MODIFIER, TokenType.ID):
            return self.parse_simple_statement()
        self.error_at(self.cur, f"Expected a statement, got {describe(self.cur)}")

    def parse_simple_statement(self):
        if self.peek().kind == TokenType.MODIFIER:
            mod = self.eat(TokenType.MODIFIER)
            typ = self.eat(TokenType.TYPE)
            ident = self.eat(TokenType.ID)
            if self.peek().kind == TokenType.ASSIGN:
                self.eat(TokenType.ASSIGN)
                expr = self.parse_expression()
                self.eat(TokenType.NEWLINE)
                return DeclAndAssignNode(mod, typ, ident, expr)
            self.eat(TokenType.NEWLINE)
            return DeclarationNode(mod, typ, ident)
        ident = self.eat(TokenType.ID)
        self.eat(TokenType.ASSIGN)
        expr = self.parse_expression()
        self.eat(TokenType.NEWLINE)
        return AssignmentNode(ident, expr)

    def parse_if(self):
        if_tok = self.eat(TokenType.IF)
        cond = self.parse_boolean_expression()
        self.eat(TokenType.NEWLINE)
        then_stmts = self.parse_block()
        else_stmts = None
        if self.peek().kind == TokenType.ELSE:
            self.eat(TokenType.ELSE)
            self.eat(TokenType.NEWLINE)
            else_stmts = self.parse_block()
        return IfNode(if_tok, cond, then_stmts, else_stmts)

    def parse_block(self):
        self.eat(TokenType.LBRACE)
        self.eat(TokenType.NEWLINE)
        if self.peek().kind == TokenType.RBRACE:
            self.error_at(self.cur, "A block must contain at least one statement")
        stmts = []
        while self.peek().kind != TokenType.RBRACE:
            if self.peek().kind == TokenType.EOF:
                self.error_at(self.cur, "Unclosed block: expected '}', got end of file")
            stmts.append(self.parse_statement())
        self.eat(TokenType.RBRACE)
        self.eat(TokenType.NEWLINE)
        return stmts

    def parse_exit(self):
        exit_tok = self.eat(TokenType.EXIT)
        ident = self.eat(TokenType.ID)
        self.eat(TokenType.NEWLINE)
        return ExitNode(exit_tok, ident)

    def parse_expression(self):
        left = self.parse_value()
        if self.peek().kind in (TokenType.EQ, TokenType.NEQ):
            op = self.eat(self.peek().kind)
            right = self.parse_value()
            return BinOpNode(left, op, right)
        return left

    def parse_boolean_expression(self):
        expr = self.parse_expression()
        if isinstance(expr, ValueNode) and expr.kind == TokenType.INT:
            raise CompileError(expr.line, expr.col,
                               f"Condition must be a boolean expression, got integer literal '{expr.value}'")
        return expr

    def parse_value(self):
        if self.peek().kind in (TokenType.ID, TokenType.INT, TokenType.BOOL_LIT):
            return ValueNode(self.eat(self.peek().kind))
        self.error_at(self.cur, f"Expected an identifier, integer or boolean literal, got {describe(self.cur)}")


def main(argv):
    if len(argv) != 3 or argv[1] != "--ast":
        sys.stderr.write("usage: python3 compiler.py --ast input.txt\n")
        return 2
    try:
        with open(argv[2], "rb") as f:
            data = f.read()
    except OSError as e:
        sys.stderr.write(f"compilation error: cannot read '{argv[2]}': {e.strerror}\n")
        return 1
    try:
        tree = Parser(Lexer(data)).parse_program()
        output = "\n".join(tree.dump()) + "\n"
    except CompileError as e:
        sys.stderr.write(f"compilation error: line {e.line}:{e.col}: {e.msg}\n")
        return 1
    sys.stdout.buffer.write(output.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
