# Emoji language — Stage 1 (lexer + parser)

A small statically-typed language written with emojis. Stage 1 implements the language design,
a hand-written byte-level lexer and a recursive-descent parser that prints the AST.
Semantic checks (including type overflow checks) and code generation belong to the next stages.

## The language

Every statement lives on its own line. `{` and `}` are always on their own lines.
Spaces and tabs between tokens are ignored; blank lines are not allowed. Both `\n` and `\r\n` line endings work.
The full grammar is in [`grammar.ebnf`](grammar.ebnf).

### Types

| Emoji | Meaning |
|-------|---------|
| 🐒 | `i32` |
| 🦍 | `i64` |
| boo!👻 | boolean |

Boolean literals: `👍` (true), `👎` (false). Integer literals are decimal digits (`0`, `42`).

### Modifiers (storage kind)

| Emoji | Meaning |
|-------|---------|
| 🚫 | constant |
| 🙂 | mutable variable |
| ☹️ | constant (immutable) variable |

### Declaration, assignment, or both

```
🙂 🐒 counter          declaration only
counter => 5           assignment
🚫 🦍 limit => 1000    declaration + assignment
☹️ boo!👻 debug => 👎
```

`=>` is the assignment operator.

### Comparison

`✅` is `==`, `❎` is `!=`. One comparison per expression.

```
🙂 boo!👻 same => counter ✅ 5
🙂 boo!👻 differs => counter ❎ limit
```

### if / else

`🤔` is `if`, `🤨` is `else`. The condition is a boolean literal, an identifier, or a comparison.
The if block and the else block each hold at least one statement; the else part is optional.

```
🤔 counter ✅ 5
{
  counter => 0
}
🤨
{
  counter => 1
}
```

### exit

`🚪 name` ends the program with the value of the given int or bool variable.

```
🚪 counter
```

### Type overflow checks

Whether a literal or a value fits its type (`🐒` = 32-bit, `🦍` = 64-bit signed) is a semantic check,
so it is implemented in the next stage. In stage 1 any digit sequence is accepted by the parser
(see the test `literal_beyond_i32_still_parses`).

## Build and run

No dependencies and no build step: Python 3.8+ is enough.

```
source ~/lcd/bin/activate
python3 compiler.py --ast input.txt
```

Output is the AST, indented by depth. Each node shows its position (`@line:column`, columns counted in characters)
and its fields (modifier, mutable flag, type, operator, name, value):

```
ProgramNode @1:1
  DeclAndAssignNode @1:1 (modifier: mutable, mutable: true, type: i32, name: x)
    ValueNode @1:10 (INT: 5)
```

On a lexical or syntax error the compiler prints a single line to stderr, prints nothing to stdout and exits
with code 1:

```
compilation error: line 3:8: Unknown character '#'
```

## Tests

```
python3 run_tests.py
```

The script runs every program in `tests/valid` (stdout must equal `NAME.expected`) and `tests/errors`
(stderr must equal `NAME.expected`, exit code non-zero, stdout empty), prints `ok` / `FAIL` for each and
lists the failed tests at the end. Its exit code is non-zero if any test fails.

- `tests/valid` — 32 programs; `tests/errors` — 39 programs (names starting `lex_` are lexical errors, `syn_` syntax errors).

## Project layout

```
compiler.py     lexer, AST classes, parser, command line
grammar.ebnf    the grammar
run_tests.py    test runner
tests/          valid/ and errors/ test cases
ai_usage.txt    AI usage disclosure
```
