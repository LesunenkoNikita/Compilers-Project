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


def main(argv):
    if len(argv) != 3 or argv[1] != "--ast":
        sys.stderr.write("usage: python3 task2compiler.py --ast input.txt\n")
        return 2
    try:
        tree = Parser(Lexer(read_source(argv[2]))).parse_program()
        output = "\n".join(tree.dump()) + "\n"
    except CompileError as e:
        report(e)
        return 1
    sys.stdout.buffer.write(output.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
