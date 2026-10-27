import sys

from llvmlite import ir, binding as llvm


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
    STRING = "STRING"
    ASSIGN = "ASSIGN"
    EQ = "EQ"
    NEQ = "NEQ"
    PLUS = "PLUS"
    MINUS = "MINUS"
    MUL = "MUL"
    IF = "IF"
    ELSE = "ELSE"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    COMMA = "COMMA"
    DOT = "DOT"
    EXIT = "EXIT"
    FUNC = "FUNC"
    RETURN = "RETURN"
    STRUCT = "STRUCT"
    METHOD = "METHOD"
    READ = "READ"
    PRINT = "PRINT"
    NEWLINE = "NEWLINE"
    EOF = "EOF"


class Token:
    def __init__(self, kind, text, line, col, value=None):
        self.kind, self.text, self.line, self.col = kind, text, line, col
        self.value = value  # decoded text of a string literal

    def __repr__(self):
        return f"Token({self.kind}, {self.text!r}, {self.line}:{self.col})"


VS16 = "️"  # emoji variation selector

KEYWORDS = [
    ("🚫", TokenType.MODIFIER),            # constant
    ("🙂", TokenType.MODIFIER),            # mutable variable
    ("☹️", TokenType.MODIFIER),  # ☹️  immutable variable (with variation selector)
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
    ("➕", TokenType.PLUS),
    ("➖", TokenType.MINUS),
    ("✖", TokenType.MUL),             # ✖ (✖️ with the variation selector below)
    ("✖" + VS16, TokenType.MUL),
    ("⚙", TokenType.FUNC),            # ⚙ function
    ("⚙" + VS16, TokenType.FUNC),
    ("🔙", TokenType.RETURN),
    ("🏰", TokenType.STRUCT),
    ("\U0001F6E0", TokenType.METHOD),      # 🛠 member function
    ("\U0001F6E0" + VS16, TokenType.METHOD),
    ("📖", TokenType.READ),
    ("\U0001F5A8", TokenType.PRINT),       # 🖨 print
    ("\U0001F5A8" + VS16, TokenType.PRINT),
    ("=>", TokenType.ASSIGN),
    ("{", TokenType.LBRACE),
    ("}", TokenType.RBRACE),
    ("(", TokenType.LPAREN),
    (")", TokenType.RPAREN),
    (",", TokenType.COMMA),
    (".", TokenType.DOT),
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

STRING_ESCAPES = {0x22: '"', 0x5C: "\\", 0x6E: "\n", 0x74: "\t"}


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

        if b == 0x22:
            return self.string_literal(line, col)

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

    def string_literal(self, line, col):
        """States: inside the literal, after a backslash; ends at the closing quote."""
        start = self.pos
        self.advance()  # opening quote
        out = bytearray()
        while True:
            b = self.peek()
            if b in (-1, 0x0A, 0x0D):
                self.error("Unterminated string literal", line, col)
            if b == 0x22:
                self.advance()
                break
            if b == 0x5C:
                esc_line, esc_col = self.line, self.col
                self.advance()
                e = self.peek()
                if e not in STRING_ESCAPES:
                    shown = chr(e) if 0x20 <= e < 0x7F else "?"
                    self.error(f"Unknown escape sequence '\\{shown}' in string literal", esc_line, esc_col)
                self.advance()
                out += STRING_ESCAPES[e].encode("ascii")
                continue
            out.append(self.advance())
        try:
            value = out.decode("utf-8")
        except UnicodeDecodeError:
            self.error("Invalid UTF-8 in string literal", line, col)
        return Token(TokenType.STRING, self.data[start:self.pos].decode("utf-8"), line, col, value)

    def unknown_character(self, b, line, col):
        n = 4 if b >= 0xF0 else 3 if b >= 0xE0 else 2 if b >= 0xC0 else 1
        try:
            ch = self.data[self.pos:self.pos + n].decode("utf-8")
        except UnicodeDecodeError:
            self.error(f"Invalid UTF-8 byte 0x{b:02X}", line, col)
        hint = " (assignment is written '=>')" if ch == "=" else ""
        self.error(f"Unknown character '{ch}'{hint}", line, col)


MODIFIER_NAMES = {"🚫": "constant", "🙂": "mutable", "☹️": "immutable"}
TYPE_NAMES = {"🐒": "i32", "🦍": "i64", "boo!👻": "bool"}
OP_NAMES = {"✅": "==", "❎": "!=", "➕": "+", "➖": "-", "✖": "*", "✖" + VS16: "*"}
OP_EMOJI = {"==": "✅", "!=": "❎", "+": "➕", "-": "➖", "*": "✖️"}


def type_name_of(tok):
    """A type token is an emoji type or the name of a structure."""
    return TYPE_NAMES.get(tok.text, tok.text)


class ASTNode:
    """Base class. Every node keeps the position of the token it came from."""

    def __init__(self, line, col):
        self.line, self.col = line, col

    def details(self):
        return ""

    def children(self):
        return []

    def head(self, depth):
        d = self.details()
        return "  " * depth + f"{type(self).__name__} @{self.line}:{self.col}" + (f" ({d})" if d else "")

    def dump(self, depth=0):
        lines = [self.head(depth)]
        for child in self.children():
            lines.extend(child.dump(depth + 1))
        return lines


def dump_section(title, nodes, depth):
    lines = ["  " * depth + title]
    for n in nodes:
        lines += n.dump(depth + 1)
    return lines


class ProgramNode(ASTNode):
    def __init__(self, line, col):
        super().__init__(line, col)
        self.statements = []  # statements, function and structure declarations in source order

    def children(self):
        return self.statements


class StmtNode(ASTNode):
    pass


class _DeclMixin:
    def init_decl(self, mod_tok, type_tok, id_tok):
        self.modifier = MODIFIER_NAMES[mod_tok.text]
        self.mutable = self.modifier == "mutable"
        self.type_tok = type_tok
        self.type_name = type_name_of(type_tok)
        self.name = id_tok.text
        self.name_tok = id_tok

    def decl_details(self):
        return (f"modifier: {self.modifier}, mutable: {str(self.mutable).lower()}, "
                f"type: {self.type_name}, name: {self.name}")


class DeclarationNode(StmtNode, _DeclMixin):
    def __init__(self, mod_tok, type_tok, id_tok):
        super().__init__(mod_tok.line, mod_tok.col)
        self.init_decl(mod_tok, type_tok, id_tok)
        self.expr = None

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
    """target is a ValueNode (a plain name) or a ChainNode of fields."""

    def __init__(self, target, arrow_tok, expr):
        super().__init__(target.line, target.col)
        self.target, self.arrow_tok, self.expr = target, arrow_tok, expr
        self.name = target.path() if isinstance(target, ChainNode) else target.value

    def details(self):
        return f"name: {self.name}"

    def children(self):
        if isinstance(self.target, ChainNode):
            return [self.target, self.expr]
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
        self.name_tok = id_tok

    def details(self):
        return f"name: {self.name}"


class ReturnNode(StmtNode):
    def __init__(self, ret_tok, expr):
        super().__init__(ret_tok.line, ret_tok.col)
        self.expr = expr

    def children(self):
        return [self.expr]


class PrintNode(StmtNode):
    def __init__(self, print_tok, expr):
        super().__init__(print_tok.line, print_tok.col)
        self.expr = expr  # an expression or a StringNode

    def children(self):
        return [self.expr]


class ReadNode(StmtNode):
    def __init__(self, read_tok, target):
        super().__init__(read_tok.line, read_tok.col)
        self.target = target  # ValueNode (a name) or ChainNode of fields

    def details(self):
        name = self.target.path() if isinstance(self.target, ChainNode) else self.target.value
        return f"target: {name}"

    def children(self):
        return [self.target]


class CallStatementNode(StmtNode):
    """A function or member call whose result is discarded."""

    def __init__(self, call):
        super().__init__(call.line, call.col)
        self.call = call

    def children(self):
        return [self.call]


class ParamNode(ASTNode):
    def __init__(self, type_tok, id_tok):
        super().__init__(type_tok.line, type_tok.col)
        self.type_tok = type_tok
        self.type_name = type_name_of(type_tok)
        self.name = id_tok.text
        self.name_tok = id_tok

    def details(self):
        return f"type: {self.type_name}, name: {self.name}"


class FunctionNode(StmtNode):
    def __init__(self, fn_tok, result_tok, name_tok, params, body):
        super().__init__(fn_tok.line, fn_tok.col)
        self.result_tok = result_tok
        self.result = type_name_of(result_tok)
        self.name = name_tok.text
        self.name_tok = name_tok
        self.params = params
        self.body = body  # statements; '🔙' may appear anywhere among them, also inside blocks

    def details(self):
        return f"name: {self.name}, result: {self.result}, params: {len(self.params)}"

    def dump(self, depth=0):
        lines = [self.head(depth)]
        for p in self.params:
            lines += p.dump(depth + 1)
        lines += dump_section("Body", self.body, depth + 1)
        return lines


class MemberFunctionNode(FunctionNode):
    def __init__(self, fn_tok, result_tok, name_tok, params, body, owner):
        super().__init__(fn_tok, result_tok, name_tok, params, body)
        self.owner = owner  # name of the structure

    def details(self):
        return f"struct: {self.owner}, " + super().details()


class FieldNode(ASTNode, _DeclMixin):
    def __init__(self, mod_tok, type_tok, id_tok, default):
        super().__init__(mod_tok.line, mod_tok.col)
        self.init_decl(mod_tok, type_tok, id_tok)
        self.default = default  # expression or None

    def details(self):
        return self.decl_details() + f", default: {str(self.default is not None).lower()}"

    def children(self):
        return [self.default] if self.default is not None else []


class StructNode(StmtNode):
    def __init__(self, struct_tok, name_tok, fields, methods):
        super().__init__(struct_tok.line, struct_tok.col)
        self.name = name_tok.text
        self.name_tok = name_tok
        self.fields, self.methods = fields, methods

    def details(self):
        return f"name: {self.name}, fields: {len(self.fields)}, member functions: {len(self.methods)}"

    def children(self):
        return sorted(self.fields + self.methods, key=lambda n: (n.line, n.col))


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


class StringNode(ExprNode):
    def __init__(self, tok):
        super().__init__(tok.line, tok.col)
        self.text = tok.value
        self.source = tok.text

    def details(self):
        return f"text: {self.source}"


class CallNode(ExprNode):
    """f(args): a call of a function, a member function of the enclosing structure, or a structure constructor."""

    def __init__(self, name_tok, args):
        super().__init__(name_tok.line, name_tok.col)
        self.name = name_tok.text
        self.args = args

    def details(self):
        return f"name: {self.name}, args: {len(self.args)}"

    def children(self):
        return self.args


class FieldStepNode(ASTNode):
    def __init__(self, name_tok):
        super().__init__(name_tok.line, name_tok.col)
        self.name = name_tok.text

    def details(self):
        return f"field: {self.name}"


class MemberCallStepNode(ASTNode):
    def __init__(self, name_tok, args):
        super().__init__(name_tok.line, name_tok.col)
        self.name = name_tok.text
        self.args = args

    def details(self):
        return f"member function: {self.name}, args: {len(self.args)}"

    def children(self):
        return self.args


class ChainNode(ExprNode):
    """base.step.step...: base is a ValueNode (a name) or a CallNode; steps are field accesses and member calls."""

    def __init__(self, base, steps):
        super().__init__(base.line, base.col)
        self.base, self.steps = base, steps

    @property
    def ends_in_call(self):
        return isinstance(self.steps[-1], MemberCallStepNode)

    def has_call(self):
        return isinstance(self.base, CallNode) or any(isinstance(s, MemberCallStepNode) for s in self.steps)

    def path(self):
        parts = [self.base.value if isinstance(self.base, ValueNode) else self.base.name + "()"]
        for s in self.steps:
            parts.append(s.name + "()" if isinstance(s, MemberCallStepNode) else s.name)
        return ".".join(parts)

    def details(self):
        return f"path: {self.path()}, ends in member call: {str(self.ends_in_call).lower()}"

    def children(self):
        return [self.base] + self.steps


EXPECTED = {
    TokenType.MODIFIER: "a modifier (🚫, 🙂 or ☹️)",
    TokenType.TYPE: "a type (🐒, 🦍 or boo!👻)",
    TokenType.ID: "an identifier",
    TokenType.INT: "an integer literal",
    TokenType.BOOL_LIT: "a boolean literal",
    TokenType.STRING: "a string literal",
    TokenType.ASSIGN: "'=>'",
    TokenType.EQ: "'✅'",
    TokenType.NEQ: "'❎'",
    TokenType.PLUS: "'➕'",
    TokenType.MINUS: "'➖'",
    TokenType.MUL: "'✖️'",
    TokenType.IF: "'🤔'",
    TokenType.ELSE: "'🤨'",
    TokenType.LBRACE: "'{'",
    TokenType.RBRACE: "'}'",
    TokenType.LPAREN: "'('",
    TokenType.RPAREN: "')'",
    TokenType.COMMA: "','",
    TokenType.DOT: "'.'",
    TokenType.EXIT: "'🚪'",
    TokenType.FUNC: "'⚙️'",
    TokenType.RETURN: "'🔙'",
    TokenType.STRUCT: "'🏰'",
    TokenType.METHOD: "'🛠️'",
    TokenType.READ: "'📖'",
    TokenType.PRINT: "'🖨️'",
    TokenType.NEWLINE: "end of line",
    TokenType.EOF: "end of file",
}

ANY_TYPE = "a type (🐒, 🦍, boo!👻 or a structure name)"


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
        self.ahead = None  # the token after cur (or the lexical error found while reading it), once peeked
        self.in_function = False  # '🔙' is allowed only inside a function body

    def peek(self):
        return self.cur

    def peek_next(self):
        """One more token of lookahead. A lexical error there is kept until the token is really consumed."""
        if self.ahead is None:
            try:
                self.ahead = self.lexer.next_token()
            except CompileError as e:
                self.ahead = e
        return None if isinstance(self.ahead, CompileError) else self.ahead

    def error_at(self, tok, msg):
        raise CompileError(tok.line, tok.col, msg)

    def eat(self, kind):
        if self.cur.kind != kind:
            self.error_at(self.cur, f"Expected {EXPECTED[kind]}, got {describe(self.cur)}")
        tok = self.cur
        if self.ahead is not None:
            nxt, self.ahead = self.ahead, None
            if isinstance(nxt, CompileError):
                raise nxt
            self.cur = nxt
        else:
            self.cur = self.lexer.next_token()
        return tok

    # ---------- program ----------

    def parse_program(self):
        first = self.peek()
        node = ProgramNode(first.line, first.col)
        node.statements.append(self.parse_top_item())
        while self.peek().kind != TokenType.EOF:
            node.statements.append(self.parse_top_item())
        return node

    def parse_top_item(self):
        kind = self.peek().kind
        if kind == TokenType.FUNC:
            return self.parse_function()
        if kind == TokenType.STRUCT:
            return self.parse_struct()
        return self.parse_statement()

    # ---------- statements ----------

    def parse_statement(self):
        kind = self.peek().kind
        if kind == TokenType.IF:
            return self.parse_if()
        if kind == TokenType.EXIT:
            return self.parse_exit()
        if kind == TokenType.PRINT:
            return self.parse_print()
        if kind == TokenType.READ:
            return self.parse_read()
        if kind in (TokenType.MODIFIER, TokenType.ID):
            return self.parse_simple_statement()
        if kind == TokenType.RETURN:
            if not self.in_function:
                self.error_at(self.cur, "'🔙' can only be used inside a function body")
            return self.parse_return()
        if kind in (TokenType.FUNC, TokenType.STRUCT):
            what = "A function" if kind == TokenType.FUNC else "A structure"
            self.error_at(self.cur, f"{what} can be declared only at the top level")
        if kind == TokenType.METHOD:
            self.error_at(self.cur, "A member function can be declared only inside a structure")
        self.error_at(self.cur, f"Expected a statement, got {describe(self.cur)}")

    def parse_simple_statement(self):
        if self.peek().kind == TokenType.MODIFIER:
            mod = self.eat(TokenType.MODIFIER)
            typ = self.parse_decl_type()
            ident = self.eat(TokenType.ID)
            if self.peek().kind == TokenType.ASSIGN:
                self.eat(TokenType.ASSIGN)
                expr = self.parse_expression()
                self.eat(TokenType.NEWLINE)
                return DeclAndAssignNode(mod, typ, ident, expr)
            self.eat(TokenType.NEWLINE)
            return DeclarationNode(mod, typ, ident)
        target = self.parse_chain()
        if isinstance(target, CallNode) or (isinstance(target, ChainNode) and target.ends_in_call):
            if self.peek().kind == TokenType.ASSIGN:
                self.error_at(self.cur, "Cannot assign to the result of a call")
            self.eat(TokenType.NEWLINE)
            return CallStatementNode(target)
        if isinstance(target, ChainNode) and target.has_call() and self.peek().kind == TokenType.ASSIGN:
            self.error_at(self.cur, "Cannot assign to a field of the result of a call")
        arrow = self.eat(TokenType.ASSIGN)
        expr = self.parse_expression()
        self.eat(TokenType.NEWLINE)
        return AssignmentNode(target, arrow, expr)

    def parse_decl_type(self):
        """DeclType: an emoji type, or a structure name when it is followed by the declared name."""
        if self.peek().kind == TokenType.TYPE:
            return self.eat(TokenType.TYPE)
        if self.peek().kind == TokenType.ID:
            nxt = self.peek_next()
            if nxt is not None and nxt.kind == TokenType.ID:
                return self.eat(TokenType.ID)
        self.error_at(self.cur, f"Expected {EXPECTED[TokenType.TYPE]}, got {describe(self.cur)}")

    def parse_any_type(self):
        if self.peek().kind in (TokenType.TYPE, TokenType.ID):
            return self.eat(self.peek().kind)
        self.error_at(self.cur, f"Expected {ANY_TYPE}, got {describe(self.cur)}")

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

    def parse_print(self):
        print_tok = self.eat(TokenType.PRINT)
        self.eat(TokenType.LPAREN)
        if self.peek().kind == TokenType.STRING:
            expr = StringNode(self.eat(TokenType.STRING))
        else:
            expr = self.parse_expression()
        self.eat(TokenType.RPAREN)
        self.eat(TokenType.NEWLINE)
        return PrintNode(print_tok, expr)

    def parse_read(self):
        read_tok = self.eat(TokenType.READ)
        self.eat(TokenType.LPAREN)
        target = self.parse_assign_target()
        self.eat(TokenType.RPAREN)
        self.eat(TokenType.NEWLINE)
        return ReadNode(read_tok, target)

    def parse_assign_target(self):
        """AssignTarget: a name followed by field names, no calls."""
        base = ValueNode(self.eat(TokenType.ID))
        steps = []
        while self.peek().kind == TokenType.DOT:
            self.eat(TokenType.DOT)
            steps.append(FieldStepNode(self.eat(TokenType.ID)))
        return ChainNode(base, steps) if steps else base

    # ---------- functions and structures ----------

    def parse_function(self):
        fn_tok = self.eat(TokenType.FUNC)
        result, name, params, body = self.parse_function_rest()
        return FunctionNode(fn_tok, result, name, params, body)

    def parse_function_rest(self):
        result = self.parse_any_type()
        name = self.eat(TokenType.ID)
        params = self.parse_params()
        self.eat(TokenType.NEWLINE)
        body = self.parse_function_body()
        return result, name, params, body

    def parse_params(self):
        self.eat(TokenType.LPAREN)
        params = []
        if self.peek().kind != TokenType.RPAREN:
            params.append(self.parse_param())
            while self.peek().kind == TokenType.COMMA:
                self.eat(TokenType.COMMA)
                params.append(self.parse_param())
        self.eat(TokenType.RPAREN)
        return params

    def parse_param(self):
        typ = self.parse_any_type()
        return ParamNode(typ, self.eat(TokenType.ID))

    def parse_function_body(self):
        self.in_function = True
        stmts = self.parse_block()
        self.in_function = False
        return stmts

    def parse_return(self):
        ret_tok = self.eat(TokenType.RETURN)
        expr = self.parse_expression()
        self.eat(TokenType.NEWLINE)
        return ReturnNode(ret_tok, expr)

    def parse_struct(self):
        struct_tok = self.eat(TokenType.STRUCT)
        name = self.eat(TokenType.ID)
        self.eat(TokenType.NEWLINE)
        self.eat(TokenType.LBRACE)
        self.eat(TokenType.NEWLINE)
        fields, methods = [], []
        while self.peek().kind != TokenType.RBRACE:
            kind = self.peek().kind
            if kind == TokenType.MODIFIER:
                fields.append(self.parse_field())
            elif kind == TokenType.METHOD:
                methods.append(self.parse_member_function(name.text))
            elif kind == TokenType.EOF:
                self.error_at(self.cur, "Unclosed block: expected '}', got end of file")
            else:
                self.error_at(self.cur, f"Expected a field or a member function, got {describe(self.cur)}")
        if not fields:
            self.error_at(self.cur, f"Structure '{name.text}' must have at least one field")
        self.eat(TokenType.RBRACE)
        self.eat(TokenType.NEWLINE)
        return StructNode(struct_tok, name, fields, methods)

    def parse_field(self):
        mod = self.eat(TokenType.MODIFIER)
        typ = self.parse_decl_type()
        ident = self.eat(TokenType.ID)
        default = None
        if self.peek().kind == TokenType.ASSIGN:
            self.eat(TokenType.ASSIGN)
            default = self.parse_expression()
        self.eat(TokenType.NEWLINE)
        return FieldNode(mod, typ, ident, default)

    def parse_member_function(self, owner):
        fn_tok = self.eat(TokenType.METHOD)
        result, name, params, body = self.parse_function_rest()
        return MemberFunctionNode(fn_tok, result, name, params, body, owner)

    # ---------- expressions ----------

    def parse_expression(self):
        left = self.parse_sum()
        if self.peek().kind in (TokenType.EQ, TokenType.NEQ):
            op = self.eat(self.peek().kind)
            right = self.parse_sum()
            return BinOpNode(left, op, right)
        return left

    def parse_boolean_expression(self):
        expr = self.parse_expression()
        if isinstance(expr, ValueNode) and expr.kind == TokenType.INT:
            raise CompileError(expr.line, expr.col,
                               f"Condition must be a boolean expression, got integer literal '{expr.value}'")
        return expr

    def parse_sum(self):
        left = self.parse_product()
        while self.peek().kind in (TokenType.PLUS, TokenType.MINUS):
            op = self.eat(self.peek().kind)
            left = BinOpNode(left, op, self.parse_product())
        return left

    def parse_product(self):
        left = self.parse_operand()
        while self.peek().kind == TokenType.MUL:
            op = self.eat(TokenType.MUL)
            left = BinOpNode(left, op, self.parse_operand())
        return left

    def parse_operand(self):
        kind = self.peek().kind
        if kind in (TokenType.INT, TokenType.BOOL_LIT):
            return self.parse_value()
        if kind == TokenType.ID:
            return self.parse_chain()
        if kind == TokenType.STRING:
            self.error_at(self.cur, "A string literal can only be printed with '🖨️'")
        self.error_at(self.cur, f"Expected an identifier, integer or boolean literal, got {describe(self.cur)}")

    def parse_value(self):
        if self.peek().kind in (TokenType.ID, TokenType.INT, TokenType.BOOL_LIT):
            return ValueNode(self.eat(self.peek().kind))
        self.error_at(self.cur, f"Expected an identifier, integer or boolean literal, got {describe(self.cur)}")

    def parse_chain(self):
        ident = self.eat(TokenType.ID)
        base = CallNode(ident, self.parse_arguments()) if self.peek().kind == TokenType.LPAREN else ValueNode(ident)
        steps = []
        while self.peek().kind == TokenType.DOT:
            self.eat(TokenType.DOT)
            name = self.eat(TokenType.ID)
            if self.peek().kind == TokenType.LPAREN:
                steps.append(MemberCallStepNode(name, self.parse_arguments()))
            else:
                steps.append(FieldStepNode(name))
        return ChainNode(base, steps) if steps else base

    def parse_arguments(self):
        self.eat(TokenType.LPAREN)
        args = []
        if self.peek().kind != TokenType.RPAREN:
            args.append(self.parse_expression())
            while self.peek().kind == TokenType.COMMA:
                self.eat(TokenType.COMMA)
                args.append(self.parse_expression())
        self.eat(TokenType.RPAREN)
        return args


def read_source(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise CompileError(0, 0, f"cannot read '{path}': {e.strerror}")


def report(e):
    if e.line:
        sys.stderr.write(f"compilation error: line {e.line}:{e.col}: {e.msg}\n")
    else:
        sys.stderr.write(f"compilation error: {e.msg}\n")


# ===================================================================
# Semantic analysis
# ===================================================================

INT_TYPES = ("i32", "i64")
SCALAR_TYPES = ("i32", "i64", "bool")
INT_MAX = {"i32": 2 ** 31 - 1, "i64": 2 ** 63 - 1}
ARITH_OPS = ("+", "-", "*")


def wider(*types):
    """The widest integer type among the given ones, None when there is none."""
    ints = [t for t in types if t in INT_TYPES]
    if not ints:
        return None
    return "i64" if "i64" in ints else "i32"


def assignable(have, want):
    """i32 widens to i64; an i64 stored into an i32 place is range-checked at run time."""
    return have == want or (have in INT_TYPES and want in INT_TYPES)


def why_not_mutable(item):
    """item: a VarInfo or a FieldInfo that is not mutable."""
    if isinstance(item, VarInfo) and item.kind == "param":
        return f"'{item.name}' is a parameter"
    return f"'{item.name}' is {item.modifier}"


def is_int_literal(e):
    return isinstance(e, ValueNode) and e.kind == TokenType.INT


class VarInfo:
    """A variable or a parameter. kind: 'global', 'local' or 'param'."""

    def __init__(self, name, type_name, modifier, kind):
        self.name, self.type, self.modifier, self.kind = name, type_name, modifier, kind
        self.mutable = modifier == "mutable" and kind != "param"
        self.storage = None  # alloca or global variable, set by the code generator


class FieldInfo:
    def __init__(self, node, index):
        self.node, self.index = node, index
        self.name, self.type = node.name, node.type_name
        self.modifier, self.mutable = node.modifier, node.mutable


class FuncInfo:
    """A function or a member function (owner is then the StructInfo)."""

    def __init__(self, node, owner=None):
        self.node, self.owner = node, owner
        self.name, self.result = node.name, node.result
        self.params = [(p.name, p.type_name) for p in node.params]
        self.direct_mutation = False  # assigns or reads into a field of its object
        self.mutating_deps = []       # member functions called on its own object (or on fields of it)
        self.mutating = False
        self.ir_func = None

    def describe(self):
        if self.owner:
            return f"member function '{self.owner.name}.{self.name}'"
        return f"function '{self.name}'"


class StructInfo:
    def __init__(self, node):
        self.node, self.name = node, node.name
        self.fields = {}   # name -> FieldInfo, in declaration order (index = position)
        self.methods = {}  # name -> FuncInfo
        self.ir_type = None

    def ctor_fields(self):
        """The fields a constructor call gives values to: the ones without a default."""
        return [f for f in self.fields.values() if f.node.default is None]


class Scope:
    def __init__(self, parent=None):
        self.vars, self.parent = {}, parent


class Analyzer:
    """Checks the AST and annotates it for the code generator:
    expressions get .type, names get .ref, declarations get .var, calls and chain steps get what they resolve to."""

    def __init__(self):
        self.structs = {}
        self.functions = {}
        self.global_scope = Scope()
        self.globals = []          # every global VarInfo, for the code generator
        self.scope = self.global_scope
        self.fn = None             # FuncInfo whose body is being checked
        self.visible_globals = {}  # globals declared above the function being checked
        self.deferred = []         # mutating-call checks, run once every member function is known

    def error(self, node, msg):
        raise CompileError(node.line, node.col, msg)

    # ---------- declarations ----------

    def check_program(self, program):
        items = program.statements
        struct_nodes = [s for s in items if isinstance(s, StructNode)]
        fn_nodes = [s for s in items if isinstance(s, FunctionNode)]
        for s in struct_nodes:
            if s.name in self.structs:
                self.error(s.name_tok, f"Structure '{s.name}' is already declared")
            self.structs[s.name] = StructInfo(s)
        for s in struct_nodes:
            self.collect_struct(self.structs[s.name])
        for f in fn_nodes:
            if f.name in self.functions:
                self.error(f.name_tok, f"Function '{f.name}' is already declared")
            if f.name in self.structs:
                self.error(f.name_tok, f"'{f.name}' is already the name of a structure")
            self.check_signature(f)
            self.functions[f.name] = FuncInfo(f)

        for item in items:
            if isinstance(item, StructNode):
                info = self.structs[item.name]
                for m in info.methods.values():
                    self.check_function(m)
            elif isinstance(item, FunctionNode):
                self.check_function(self.functions[item.name])
            else:
                self.check_stmt(item)

        self.resolve_mutating()
        for check in self.deferred:
            check()

    def check_type(self, tok, type_name):
        if type_name not in SCALAR_TYPES and type_name not in self.structs:
            self.error(tok, f"Unknown type '{type_name}'")

    def check_signature(self, fn_node):
        self.check_type(fn_node.result_tok, fn_node.result)
        seen = set()
        for p in fn_node.params:
            self.check_type(p.type_tok, p.type_name)
            if p.name in seen:
                self.error(p.name_tok, f"Parameter '{p.name}' is already declared")
            seen.add(p.name)

    def collect_struct(self, info):
        declared_above = list(self.structs)[:list(self.structs).index(info.name)]
        for f in info.node.fields:
            if f.name in info.fields:
                self.error(f.name_tok, f"Structure '{info.name}' already has a member named '{f.name}'")
            if f.type_name not in SCALAR_TYPES:
                self.check_type(f.type_tok, f.type_name)
                if f.type_name not in declared_above:
                    self.error(f.type_tok, f"Structure '{f.type_name}' must be declared above structure "
                                           f"'{info.name}' to be the type of a field")
            if f.default is None and f.modifier == "constant":
                self.error(f.name_tok, f"Constant field '{f.name}' must be given a value in its declaration")
            if f.default is not None:
                if f.type_name not in SCALAR_TYPES:
                    self.error(f.default, f"Field '{f.name}' of structure type cannot have a default value")
                if not self.is_literal_expr(f.default):
                    self.error(f.default, f"Default value of field '{f.name}' must be built from literals and operators")
                self.expect_type(f.default, f.type_name,
                                 lambda t: f"Default value of field '{f.name}' must be {f.type_name}, got {t}")
            info.fields[f.name] = FieldInfo(f, len(info.fields))
        for m in info.node.methods:
            if m.name in info.fields or m.name in info.methods:
                self.error(m.name_tok, f"Structure '{info.name}' already has a member named '{m.name}'")
            self.check_signature(m)
            info.methods[m.name] = FuncInfo(m, info)

    def is_literal_expr(self, e):
        if isinstance(e, BinOpNode):
            return self.is_literal_expr(e.left) and self.is_literal_expr(e.right)
        return isinstance(e, ValueNode) and e.kind != TokenType.ID

    def is_constant_expr(self, e):
        """Literals, operators and other 🚫 constants."""
        if isinstance(e, BinOpNode):
            return self.is_constant_expr(e.left) and self.is_constant_expr(e.right)
        if isinstance(e, ValueNode):
            if e.kind != TokenType.ID:
                return True
            kind, info = e.ref
            return kind == "var" and info.modifier == "constant" and info.kind != "param"
        return False

    def check_function(self, fi):
        node = fi.node
        outer = (self.scope, self.fn, self.visible_globals)
        self.visible_globals = dict(self.global_scope.vars)
        self.fn, self.scope = fi, Scope()
        for p in node.params:
            p.var = VarInfo(p.name, p.type_name, "immutable", "param")
            self.scope.vars[p.name] = p.var
        for s in node.body:
            self.check_stmt(s)
        if not self.always_leaves(node.body):
            self.error(node.name_tok, f"{fi.describe()[0].upper()}{fi.describe()[1:]} can reach its end "
                                      f"without '🔙': every path must leave it with a value")
        self.scope, self.fn, self.visible_globals = outer

    def always_leaves(self, stmts):
        """True when every path through stmts ends in '🔙' or '🚪' (an if counts only with both branches)."""
        for s in stmts:
            if isinstance(s, (ReturnNode, ExitNode)):
                return True
            if isinstance(s, IfNode) and s.else_stmts is not None \
                    and self.always_leaves(s.then_stmts) and self.always_leaves(s.else_stmts):
                return True
        return False

    # ---------- names ----------

    def lookup(self, name):
        """Parameters and locals (innermost block first), then the fields of the object, then the globals."""
        s = self.scope
        while s is not None:
            if name in s.vars:
                return "var", s.vars[name]
            s = s.parent
        if self.fn is not None:
            if self.fn.owner is not None and name in self.fn.owner.fields:
                return "field", self.fn.owner.fields[name]
            if name in self.visible_globals:
                return "var", self.visible_globals[name]
        return None

    def resolve_name(self, node):
        ref = self.lookup(node.value)
        if ref is None:
            self.error(node, f"Unknown variable '{node.value}'")
        node.ref = ref
        return ref

    # ---------- statements ----------

    def check_block(self, stmts):
        self.scope = Scope(self.scope)
        for s in stmts:
            self.check_stmt(s)
        self.scope = self.scope.parent

    def check_stmt(self, node):
        if isinstance(node, (DeclarationNode, DeclAndAssignNode)):
            self.check_declaration(node)
        elif isinstance(node, AssignmentNode):
            t = self.check_target(node.target, "assign to")
            self.expect_type(node.expr, t,
                             lambda have: f"Cannot assign a value of type {have} to '{node.name}' of type {t}")
        elif isinstance(node, IfNode):
            t = self.expr_type(node.cond)
            if t != "bool":
                self.error(node.cond, f"Condition must be a boolean expression, got {t}")
            self.check_block(node.then_stmts)
            if node.else_stmts is not None:
                self.check_block(node.else_stmts)
        elif isinstance(node, ExitNode):
            node.target = ValueNode(node.name_tok)
            t = self.expr_type(node.target)
            if t not in SCALAR_TYPES:
                self.error(node.name_tok, f"'🚪' needs an integer or boolean variable, got '{node.name}' of type {t}")
        elif isinstance(node, PrintNode):
            if not isinstance(node.expr, StringNode):
                self.expr_type(node.expr)
        elif isinstance(node, ReadNode):
            t = self.check_target(node.target, "read into")
            if t not in INT_TYPES:
                self.error(node.target, f"'📖' reads an integer, but '{self.target_name(node.target)}' is {t}")
        elif isinstance(node, CallStatementNode):
            self.expr_type(node.call)
        elif isinstance(node, ReturnNode):
            fi = self.fn
            self.expect_type(node.expr, fi.result,
                             lambda t: f"{fi.describe()[0].upper()}{fi.describe()[1:]} must return {fi.result}, got {t}")
        else:
            self.error(node, f"Unexpected {type(node).__name__} here")

    def check_declaration(self, node):
        self.check_type(node.type_tok, node.type_name)
        if node.expr is None:
            if node.type_name not in SCALAR_TYPES:
                self.error(node.name_tok, f"Object '{node.name}' of structure '{node.type_name}' "
                                          f"must be created with a value")
            if node.modifier != "mutable":
                self.error(node.name_tok, f"{node.modifier.capitalize()} variable '{node.name}' "
                                          f"must be given a value in its declaration")
        else:
            self.expect_type(node.expr, node.type_name,
                             lambda t: f"Cannot assign a value of type {t} to '{node.name}' of type {node.type_name}")
            if node.modifier == "constant" and not self.is_constant_expr(node.expr):
                self.error(node.expr, f"Constant '{node.name}' needs a constant value "
                                      f"(literals, operators and other 🚫 constants)")
        if node.name in self.scope.vars:
            self.error(node.name_tok, f"Variable '{node.name}' is already declared in this scope")
        is_global = self.fn is None and self.scope is self.global_scope
        node.var = VarInfo(node.name, node.type_name, node.modifier, "global" if is_global else "local")
        self.scope.vars[node.name] = node.var
        if is_global:
            self.globals.append(node.var)

    @staticmethod
    def target_name(target):
        return target.path() if isinstance(target, ChainNode) else target.value

    def check_target(self, target, action):
        """A name or a field chain that is assigned: every step must be mutable. Returns its type."""
        base = target.base if isinstance(target, ChainNode) else target
        kind, info = self.resolve_name(base)
        elements = [(base, info)]
        t = info.type
        for step in (target.steps if isinstance(target, ChainNode) else []):
            field = self.field_of(t, step)
            step.field = field
            elements.append((step, field))
            t = field.type
        base.type = elements[0][1].type
        if isinstance(target, ChainNode):
            target.type = t
        for node, item in elements:
            if not item.mutable:
                self.error(node, f"Cannot {action} '{self.target_name(target)}': {why_not_mutable(item)}")
        if kind == "field":
            self.fn.direct_mutation = True
        return t

    def field_of(self, type_name, step):
        if type_name not in self.structs:
            self.error(step, f"Cannot access field '{step.name}' of a value of type {type_name}")
        struct = self.structs[type_name]
        if step.name not in struct.fields:
            if step.name in struct.methods:
                self.error(step, f"'{step.name}' is a member function of '{type_name}', call it with '()'")
            self.error(step, f"Structure '{type_name}' has no field '{step.name}'")
        return struct.fields[step.name]

    # ---------- expressions ----------

    def expect_type(self, expr, want, message):
        t = self.expr_type(expr, want)
        if not assignable(t, want):
            self.error(expr, message(t))
        return t

    def expr_type(self, e, want=None):
        e.type = self.compute_type(e, want)
        return e.type

    def compute_type(self, e, want):
        if isinstance(e, ValueNode):
            if e.kind == TokenType.BOOL_LIT:
                return "bool"
            if e.kind == TokenType.INT:
                e.const_value = int(e.value)
                t = want if want in INT_TYPES else ("i32" if e.const_value <= INT_MAX["i32"] else "i64")
                if e.const_value > INT_MAX[t]:
                    self.error(e, f"Integer literal {e.value} does not fit in {t} "
                                  f"(the largest {t} is {INT_MAX[t]})")
                return t
            kind, info = self.resolve_name(e)
            return info.type
        if isinstance(e, BinOpNode):
            return self.binop_type(e, want)
        if isinstance(e, CallNode):
            return self.call_type(e)
        if isinstance(e, ChainNode):
            return self.chain_type(e)
        self.error(e, "A string literal can only be printed with '🖨️'")

    def binop_type(self, e, want):
        hint = want if e.op in ARITH_OPS and want in INT_TYPES else None
        left, right = e.left, e.right
        # an integer literal operand takes the type of the other operand: 'big ➕ 1' is i64 arithmetic,
        # and the expected type reaches only literals with no other operand to follow
        if is_int_literal(left) and not is_int_literal(right):
            rt = self.expr_type(right, hint)
            lt = self.expr_type(left, rt if rt in INT_TYPES else None)
        elif is_int_literal(right) and not is_int_literal(left):
            lt = self.expr_type(left, hint)
            rt = self.expr_type(right, lt if lt in INT_TYPES else None)
        else:
            lt = self.expr_type(left, hint)
            rt = self.expr_type(right, hint)
        sym = OP_EMOJI[e.op]
        if e.op in ARITH_OPS:
            if lt not in INT_TYPES or rt not in INT_TYPES:
                bad = lt if lt not in INT_TYPES else rt
                self.error(e, f"Operator '{sym}' needs integer operands, got {bad}")
            e.operand_type = wider(lt, rt)
            return e.operand_type
        if lt in INT_TYPES and rt in INT_TYPES:
            e.operand_type = wider(lt, rt)
        elif lt == rt == "bool":
            e.operand_type = "bool"
        elif lt == rt:
            self.error(e, f"Cannot compare objects of structure '{lt}' with '{sym}'")
        else:
            self.error(e, f"Cannot compare {lt} with {rt}")
        return "bool"

    def check_args(self, node, args, params, what):
        """what(i, name) describes the i-th parameter for an error message."""
        if len(args) != len(params):
            noun = "argument" if len(params) == 1 else "arguments"
            self.error(node, f"{what(None, None)} expects {len(params)} {noun}, got {len(args)}")
        for i, (arg, (pname, ptype)) in enumerate(zip(args, params), 1):
            self.expect_type(arg, ptype, lambda t: f"{what(i, pname)} must be {ptype}, got {t}")

    def call_type(self, e):
        owner = self.fn.owner if self.fn is not None else None
        if owner is not None and e.name in owner.methods:
            m = owner.methods[e.name]
            e.target = ("this_method", m)
            self.fn.mutating_deps.append(m)
            self.check_args(e, e.args, m.params, self.param_desc(m))
            return m.result
        if e.name in self.functions:
            f = self.functions[e.name]
            e.target = ("function", f)
            self.check_args(e, e.args, f.params, self.param_desc(f))
            return f.result
        if e.name in self.structs:
            s = self.structs[e.name]
            e.target = ("construct", s)
            fields = [(f.name, f.type) for f in s.ctor_fields()]

            def what(i, name):
                return f"Structure '{s.name}'" if i is None else f"Value for field '{name}' of '{s.name}'"
            if len(e.args) != len(fields):
                noun = "value" if len(fields) == 1 else "values"
                self.error(e, f"Structure '{s.name}' expects {len(fields)} {noun}, got {len(e.args)}")
            self.check_args(e, e.args, fields, what)
            return s.name
        self.error(e, f"Unknown function '{e.name}'")

    @staticmethod
    def param_desc(fi):
        def what(i, name):
            d = fi.describe()
            return d[0].upper() + d[1:] if i is None else f"Argument {i} ('{name}') of {d}"
        return what

    def chain_type(self, e):
        base = e.base
        t = self.expr_type(base)
        # receiver tracking for mutating calls: the named elements of the chain so far
        if isinstance(base, ValueNode):
            kind, info = base.ref
            path, from_field = [(base, info)], kind == "field"
        else:
            path, from_field = None, False  # a temporary value
        names = [self.target_name(base) if isinstance(base, ValueNode) else base.name + "()"]
        for step in e.steps:
            if isinstance(step, FieldStepNode):
                field = self.field_of(t, step)
                step.field = field
                if path is not None:
                    path.append((step, field))
                names.append(step.name)
                t = field.type
                continue
            if t not in self.structs:
                self.error(step, f"Cannot call member function '{step.name}' on a value of type {t}")
            struct = self.structs[t]
            if step.name not in struct.methods:
                if step.name in struct.fields:
                    self.error(step, f"'{step.name}' is a field of '{t}', not a member function")
                self.error(step, f"Structure '{t}' has no member function '{step.name}'")
            m = struct.methods[step.name]
            step.method = m
            self.check_args(step, step.args, m.params, self.param_desc(m))
            self.defer_mutating_check(step, m, list(path) if path is not None else None, ".".join(names), from_field)
            names.append(step.name + "()")
            path, from_field = None, False
            t = m.result
        return t

    def defer_mutating_check(self, step, m, path, receiver, from_field):
        fn = self.fn
        if path is not None and from_field and all(item.mutable for _, item in path):
            fn.mutating_deps.append(m)  # calling it changes a field of our own object

        def check():
            if not m.mutating:
                return
            if path is None:
                self.error(step, f"Cannot call mutating member function '{m.name}' on a temporary value")
            for node, item in path:
                if not item.mutable:
                    self.error(step, f"Cannot call mutating member function '{m.name}' on '{receiver}': "
                                     f"{why_not_mutable(item)}")
        self.deferred.append(check)

    def resolve_mutating(self):
        methods = [m for s in self.structs.values() for m in s.methods.values()]
        for m in methods:
            m.mutating = m.direct_mutation
        changed = True
        while changed:
            changed = False
            for m in methods:
                if not m.mutating and any(d.mutating for d in m.mutating_deps):
                    m.mutating = changed = True


# ===================================================================
# Code generation (llvmlite builder)
# ===================================================================

I1, I8, I32, I64 = ir.IntType(1), ir.IntType(8), ir.IntType(32), ir.IntType(64)
I8P = I8.as_pointer()
VOID = ir.VoidType()
SCALAR_FMT = {"i32": "%d", "i64": "%lld", "bool": "%s"}
OVERFLOW_OPS = {"+": "sadd_with_overflow", "-": "ssub_with_overflow", "*": "smul_with_overflow"}


class CodeGen:
    def __init__(self, analyzer):
        self.a = analyzer
        self.module = ir.Module(name="emoji")
        self.module.triple = llvm.get_process_triple()
        self.strings = {}
        self.builder = None
        self.this_ptr = None
        c_type = ir.FunctionType(I32, [I8P], var_arg=True)  # int f(const char *fmt, ...)
        self.printf = ir.Function(self.module, c_type, name="printf")
        self.scanf = ir.Function(self.module, c_type, name="scanf")
        self.dprintf = ir.Function(self.module, ir.FunctionType(I32, [I32, I8P], var_arg=True), name="dprintf")
        self.fflush = ir.Function(self.module, ir.FunctionType(I32, [I8P]), name="fflush")
        self.exit = ir.Function(self.module, ir.FunctionType(VOID, [I32]), name="exit")
        self.fail = self.make_fail()

    # ---------- helpers ----------

    def llvm_type(self, t):
        return {"i32": I32, "i64": I64, "bool": I1}.get(t) or self.a.structs[t].ir_type

    def cstr(self, text):
        """A pointer to a global constant holding the zero-terminated text."""
        if text not in self.strings:
            data = bytearray(text.encode("utf-8") + b"\0")
            arr = ir.ArrayType(I8, len(data))
            g = ir.GlobalVariable(self.module, arr, name=f"str.{len(self.strings)}")
            g.linkage = "private"
            g.global_constant = True
            g.unnamed_addr = True
            g.initializer = ir.Constant(arr, data)
            self.strings[text] = g.gep([ir.Constant(I32, 0), ir.Constant(I32, 0)])
        return self.strings[text]

    def make_fail(self):
        """rt.fail(msg, line, col): report a runtime error on stderr and exit with code 1."""
        fn = ir.Function(self.module, ir.FunctionType(VOID, [I8P, I32, I32]), name="rt.fail")
        fn.linkage = "internal"
        fn.attributes.add("noreturn")
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        msg, line, col = fn.args
        b.call(self.fflush, [ir.Constant(I8P, None)])
        b.call(self.dprintf, [ir.Constant(I32, 2), self.cstr("runtime error: line %d:%d: %s\n"), line, col, msg])
        b.call(self.exit, [ir.Constant(I32, 1)])
        b.unreachable()
        return fn

    def runtime_error(self, node, msg):
        self.builder.call(self.fail, [self.cstr(msg), ir.Constant(I32, node.line), ir.Constant(I32, node.col)])

    def alloca(self, ty, name=""):
        """Allocas go to the start of the entry block, so a block that runs twice does not grow the stack."""
        b = self.builder
        cur = b.block
        b.position_at_start(b.function.entry_basic_block)
        slot = b.alloca(ty, name=name)
        b.position_at_end(cur)
        return slot

    def coerce(self, value, have, want, node):
        b = self.builder
        if have == "i32" and want == "i64":
            return b.sext(value, I64)
        if have == "i64" and want == "i32":
            narrow = b.trunc(value, I32)
            with b.if_then(b.icmp_signed("!=", b.sext(narrow, I64), value), likely=False):
                self.runtime_error(node, "an i64 value does not fit in i32")
            return narrow
        return value

    def field_ptr(self, ptr, field):
        """A field is reached with a gep by its index from the symbol table."""
        return self.builder.gep(ptr, [ir.Constant(I32, 0), ir.Constant(I32, field.index)],
                                inbounds=True, name=field.name)

    def printf_call(self, fmt, *args):
        self.builder.call(self.printf, [self.cstr(fmt), *args])

    def bool_text(self, value):
        return self.builder.select(value, self.cstr("true"), self.cstr("false"))

    # ---------- module ----------

    def generate(self, program):
        a = self.a
        for s in a.structs.values():
            s.ir_type = self.module.context.get_identified_type(f"struct.{s.name}")
        for s in a.structs.values():
            s.ir_type.set_body(*[self.llvm_type(f.type) for f in s.fields.values()])

        # declare every function before generating any body, so a call to a later function resolves
        methods = [m for s in a.structs.values() for m in s.methods.values()]
        for m in methods:
            ty = ir.FunctionType(self.llvm_type(m.result),
                                 [m.owner.ir_type.as_pointer()] + [self.llvm_type(t) for _, t in m.params])
            m.ir_func = ir.Function(self.module, ty, name=f"{m.owner.name}.{m.name}")
        for f in a.functions.values():
            ty = ir.FunctionType(self.llvm_type(f.result), [self.llvm_type(t) for _, t in f.params])
            f.ir_func = ir.Function(self.module, ty, name=f"fn_{f.name}")

        for v in a.globals:
            ty = self.llvm_type(v.type)
            g = ir.GlobalVariable(self.module, ty, name=f"g.{v.name}")
            g.initializer = ir.Constant(ty, None)
            g.linkage = "internal"
            v.storage = g

        for fi in methods + list(a.functions.values()):
            self.gen_function(fi)

        main = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.builder = ir.IRBuilder(main.append_basic_block("entry"))
        self.this_ptr = None
        for item in program.statements:
            if not isinstance(item, (FunctionNode, StructNode)):
                self.gen_stmt(item)
        if not self.builder.block.is_terminated:
            self.builder.ret(ir.Constant(I32, 0))
        return self.module

    def gen_function(self, fi):
        f = fi.ir_func
        self.builder = ir.IRBuilder(f.append_basic_block("entry"))
        args = list(f.args)
        self.current_fn = fi
        self.this_ptr = None
        if fi.owner is not None:
            self.this_ptr = args.pop(0)
            self.this_ptr.name = "this"
        for p, arg in zip(fi.node.params, args):
            arg.name = p.name
            slot = self.alloca(arg.type, name=f"{p.name}.addr")
            self.builder.store(arg, slot)
            p.var.storage = slot
        self.gen_stmts(fi.node.body)
        if not self.builder.block.is_terminated:
            self.builder.unreachable()  # the semantic pass proved every path returns: this block is dead

    # ---------- statements ----------

    def gen_stmts(self, stmts):
        for s in stmts:
            self.gen_stmt(s)

    def gen_stmt(self, node):
        b = self.builder
        if isinstance(node, (DeclarationNode, DeclAndAssignNode)):
            var = node.var
            if var.storage is None:
                var.storage = self.alloca(self.llvm_type(var.type), name=var.name)
            if node.expr is not None:
                value = self.coerce(self.gen_expr(node.expr), node.expr.type, var.type, node.expr)
            else:
                value = ir.Constant(self.llvm_type(var.type), 0)
            b.store(value, var.storage)
        elif isinstance(node, AssignmentNode):
            value = self.coerce(self.gen_expr(node.expr), node.expr.type, node.target.type, node.expr)
            b.store(value, self.address_of(node.target))
        elif isinstance(node, IfNode):
            self.gen_if(node)
        elif isinstance(node, ExitNode):
            self.gen_exit(node)
        elif isinstance(node, PrintNode):
            self.gen_print(node.expr)
        elif isinstance(node, ReadNode):
            self.gen_read(node)
        elif isinstance(node, CallStatementNode):
            self.gen_expr(node.call)
        elif isinstance(node, ReturnNode):
            fi = self.current_fn
            b.ret(self.coerce(self.gen_expr(node.expr), node.expr.type, fi.result, node.expr))
            b.position_at_end(b.append_basic_block("after_return"))  # statements after 🔙 are never run

    def gen_if(self, node):
        b = self.builder
        cond = self.gen_expr(node.cond)
        then_bb = b.append_basic_block("then")
        else_bb = b.append_basic_block("else") if node.else_stmts is not None else None
        end_bb = b.append_basic_block("endif")
        b.cbranch(cond, then_bb, else_bb or end_bb)
        for bb, stmts in ((then_bb, node.then_stmts), (else_bb, node.else_stmts)):
            if bb is None:
                continue
            b.position_at_end(bb)
            self.gen_stmts(stmts)
            if not b.block.is_terminated:
                b.branch(end_bb)
        b.position_at_end(end_bb)

    def gen_exit(self, node):
        b = self.builder
        t = node.target.type
        value = self.gen_expr(node.target)
        shown = self.bool_text(value) if t == "bool" else value
        self.printf_call(f"Program exit with result {SCALAR_FMT[t]}\n", shown)
        if t == "bool":
            code = b.zext(value, I32)
        elif t == "i64":
            code = b.trunc(value, I32)
        else:
            code = value
        b.call(self.exit, [code])
        b.unreachable()
        b.position_at_end(b.append_basic_block("after_exit"))  # statements after 🚪 are never run

    def gen_print(self, expr):
        if isinstance(expr, StringNode):
            self.printf_call("%s\n", self.cstr(expr.text))
            return
        t = expr.type
        if t in SCALAR_TYPES:
            value = self.gen_expr(expr)
            self.printf_call(SCALAR_FMT[t] + "\n", self.bool_text(value) if t == "bool" else value)
            return
        self.print_object(self.address_of(expr), self.a.structs[t])
        self.printf_call("\n")

    def print_object(self, ptr, struct):
        """Point{x: 1, y: 2}: walks the field table, one gep, load and printf per field."""
        self.printf_call(f"{struct.name}{{")
        for i, field in enumerate(struct.fields.values()):
            sep = ", " if i else ""
            fptr = self.field_ptr(ptr, field)
            if field.type in SCALAR_TYPES:
                value = self.builder.load(fptr)
                if field.type == "bool":
                    value = self.bool_text(value)
                self.printf_call(f"{sep}{field.name}: {SCALAR_FMT[field.type]}", value)
            else:
                self.printf_call(f"{sep}{field.name}: ")
                self.print_object(fptr, self.a.structs[field.type])
        self.printf_call("}")

    def gen_read(self, node):
        b = self.builder
        slot = self.address_of(node.target)
        got = b.call(self.scanf, [self.cstr(SCALAR_FMT[node.target.type]), slot])
        with b.if_then(b.icmp_signed("!=", got, ir.Constant(I32, 1)), likely=False):
            self.runtime_error(node, "cannot read an integer from the input")

    # ---------- expressions ----------

    def address_of(self, e):
        """A pointer to the value of e; a temporary is stored to a fresh slot first."""
        if isinstance(e, ValueNode) and e.kind == TokenType.ID:
            kind, info = e.ref
            if kind == "field":
                return self.field_ptr(self.this_ptr, info)
            return info.storage
        if isinstance(e, ChainNode):
            return self.gen_chain(e, want_ptr=True)
        value = self.gen_expr(e)
        slot = self.alloca(value.type, name="tmp")
        self.builder.store(value, slot)
        return slot

    def gen_expr(self, e):
        b = self.builder
        if isinstance(e, ValueNode):
            if e.kind == TokenType.INT:
                return ir.Constant(self.llvm_type(e.type), e.const_value)
            if e.kind == TokenType.BOOL_LIT:
                return ir.Constant(I1, 1 if e.value == "true" else 0)
            return b.load(self.address_of(e), name=e.value)
        if isinstance(e, BinOpNode):
            return self.gen_binop(e)
        if isinstance(e, CallNode):
            return self.gen_call(e)
        if isinstance(e, ChainNode):
            return self.gen_chain(e, want_ptr=False)
        raise CompileError(e.line, e.col, "internal error: cannot generate this expression")

    def gen_binop(self, e):
        b = self.builder
        t = e.operand_type
        left = self.coerce(self.gen_expr(e.left), e.left.type, t, e.left)
        right = self.coerce(self.gen_expr(e.right), e.right.type, t, e.right)
        if e.op in ARITH_OPS:
            pair = getattr(b, OVERFLOW_OPS[e.op])(left, right)
            with b.if_then(b.extract_value(pair, 1), likely=False):
                self.runtime_error(e, f"integer overflow in '{OP_EMOJI[e.op]}' ({t})")
            return b.extract_value(pair, 0)
        if t == "bool":
            return b.icmp_unsigned(e.op, left, right)
        return b.icmp_signed(e.op, left, right)

    def gen_args(self, args, params):
        return [self.coerce(self.gen_expr(a), a.type, t, a) for a, (_, t) in zip(args, params)]

    def gen_call(self, e):
        b = self.builder
        kind, info = e.target
        if kind == "function":
            return b.call(info.ir_func, self.gen_args(e.args, info.params))
        if kind == "this_method":
            return b.call(info.ir_func, [self.this_ptr] + self.gen_args(e.args, info.params))
        slot = self.alloca(info.ir_type, name=f"new.{info.name}")
        values = iter(e.args)
        for field in info.fields.values():
            src = field.node.default if field.node.default is not None else next(values)
            b.store(self.coerce(self.gen_expr(src), src.type, field.type, src), self.field_ptr(slot, field))
        return b.load(slot)

    def gen_chain(self, e, want_ptr):
        """Walks base.step.step: fields are geps, a member call gets the address of its object."""
        b = self.builder
        ptr = self.address_of(e.base)
        for i, step in enumerate(e.steps):
            if isinstance(step, FieldStepNode):
                ptr = self.field_ptr(ptr, step.field)
                continue
            m = step.method
            value = b.call(m.ir_func, [ptr] + self.gen_args(step.args, m.params))
            if i == len(e.steps) - 1 and not want_ptr:
                return value
            ptr = self.alloca(value.type, name="tmp")
            b.store(value, ptr)
        return ptr if want_ptr else b.load(ptr)


def compile_program(source):
    tree = Parser(Lexer(source)).parse_program()
    analyzer = Analyzer()
    analyzer.check_program(tree)
    return str(CodeGen(analyzer).generate(tree))


USAGE = "usage: python3 compiler.py input.txt output.ll\n       python3 compiler.py --ast input.txt\n"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(USAGE)
        return 2
    try:
        if argv[1] == "--ast":
            tree = Parser(Lexer(read_source(argv[2]))).parse_program()
            output = "\n".join(tree.dump()) + "\n"
            sys.stdout.buffer.write(output.encode("utf-8"))
            return 0
        ir_text = compile_program(read_source(argv[1]))
    except CompileError as e:
        report(e)
        return 1
    except RecursionError:
        sys.stderr.write("compilation error: the program is nested too deeply\n")
        return 1
    except Exception as e:  # a bug in the compiler is still reported as one line, never a traceback
        sys.stderr.write(f"compilation error: internal compiler error: {type(e).__name__}: {e}\n")
        return 1
    try:
        with open(argv[2], "w", encoding="utf-8") as f:
            f.write(ir_text)
    except OSError as e:
        sys.stderr.write(f"compilation error: cannot write '{argv[2]}': {e.strerror}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
