# Emoji language — Stage 2 (functions, structures, code generation)

A small statically-typed language written with emojis. The compiler is a hand-written byte-level lexer (a state
machine), a recursive-descent parser (one function per grammar rule), a semantic pass with a symbol table, and an
LLVM IR generator built with the `llvmlite.ir` builder. Compiled programs run with `lli` or `llc` + `clang`.

- [`grammar.ebnf`](grammar.ebnf) — the full grammar with its lexical rules
- [`README_TASK1.md`](README_TASK1.md) — Stage 2 Task 1 alone: the new constructs and the semantic rules

## The language — Stage 1 constructs

Every statement lives on its own line. `{` and `}` are always on their own lines.
Spaces and tabs between tokens are ignored; blank lines are not allowed. Both `\n` and `\r\n` line endings work.

### Types

| Emoji | Meaning |
|-------|---------|
| 🐒 | `i32` |
| 🦍 | `i64` |
| boo!👻 | boolean |
| a structure name | an object of that structure (Stage 2) |

Boolean literals: `👍` (true), `👎` (false). Integer literals are decimal digits (`0`, `42`, `007`).

### Modifiers (storage kind)

| Emoji | Meaning |
|-------|---------|
| 🚫 | constant: value given in the declaration, from a constant expression |
| 🙂 | mutable variable |
| ☹️ | immutable variable: value given in the declaration, never reassigned |

### Declaration, assignment, or both

```
🙂 🐒 counter          declaration only (a mutable integer starts at 0, a bool at 👎)
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

`🤔` is `if`, `🤨` is `else`. The condition is a bool expression (a bare integer literal is a syntax error).
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

`🚪 name` prints `Program exit with result V` and ends the program with the value V of the given int or bool
variable as its exit status (bool: 1 / 0).

```
🚪 counter
```

## The language — Stage 2 constructs

Stage 2 keeps every construct of Stage 1 and adds functions, structures with fields
and member functions, `print`, `read` and integer arithmetic. The full grammar is in [`grammar.ebnf`](grammar.ebnf).
Each rule below names the tests that follow it (`tests/valid/…`) and that break it (`tests/errors/…`).

### New tokens

| Emoji / text | Meaning |
|--------------|---------|
| `⚙️` | declare a function |
| `🔙` | leave the function with a value (`return`) |
| `🏰` | declare a structure |
| `🛠️` | declare a member function (inside a structure) |
| `🖨️` | print |
| `📖` | read |
| `➕` `➖` `✖️` | `+` `-` `*` |
| `(` `)` `,` `.` | parameter / argument lists, field access |
| `"text"` | string literal (only inside `🖨️(…)`); escapes `\"` `\\` `\n` `\t` |

The variation selector U+FE0F after `⚙`, `🛠`, `🖨` and `✖` is optional. A structure name is used as a type:
`🙂 Point p => Point(1, 2)`.

### Functions

```
⚙️ 🦍 fact(🦍 n)
{
  🤔 n ✅ 0
  {
    🔙 1
  }
  🔙 n ✖️ fact(n ➖ 1)
}
🖨️(fact(20))
```

Syntax: `⚙️ ResultType name(Type param, …)`, then a body in braces (at least one statement). `🔙 value` is
`return value`: it leaves the function at once with that value and may stand anywhere in the body, also inside
`🤔` / `🤨` blocks; statements after it in the same block are never run. A function is declared only at the top level. A call is an expression,
its arguments are expressions and may be calls themselves: `add(add(1, 2), twice(3))`. A call whose result is not
needed can stand alone as a statement: `p.shift(1)`.

### Structures with fields

```
🏰 Point
{
  🙂 🐒 x
  🙂 🐒 y
}
🏰 Circle
{
  🙂 Point center
  ☹️ 🐒 radius
  🚫 boo!👻 round => 👍
}
🙂 Circle c => Circle(Point(1, 2), 5)
c.center.x => 10
🖨️(c.center.x)
```

A field is declared like a variable: a modifier (`🙂` mutable, `☹️` immutable, `🚫` constant), a type, a name and an
optional `=> value`. An object is created with `Name(v1, v2, …)`: one value for every field that has no `=> value`,
in declaration order; a field with `=> value` starts with that value. So every field gets a value.
Fields are reached by name, also through a chain: `c.center.x`.

### Member functions

```
🏰 Point
{
  🙂 🐒 x
  🙂 🐒 y
  🛠️ 🐒 d2()
  {
    🔙 x ✖️ x ➕ y ✖️ y
  }
  🛠️ 🐒 shift(🐒 dx)
  {
    x => x ➕ dx
    🔙 x
  }
}
🙂 Point p => Point(3, 4)
p.shift(1)
🖨️(p.d2())
```

Declared inside a structure with `🛠️`, otherwise written like a function. Inside, the fields and the other member
functions of the structure are used by plain name (`x`, `d2()`). A member function is called on an object:
`p.d2()`, also at the end or in the middle of a chain: `make(1, 2).plus(a).len2()`.

### print and read

```
🖨️("Point:")
🖨️(p)
🖨️(p.x ✅ 4)
📖(p.x)
```

`🖨️(value)` prints an integer, a bool, a string literal or an object. `📖(target)` reads one integer from standard
input into a variable or a field chain.

### Arithmetic

`➕`, `➖`, `✖️` on integers; `✖️` binds tighter than `➕` and `➖`, which bind tighter than `✅` / `❎`
(still at most one comparison per expression). There are no negative literals: write `0 ➖ 5`.


## Rules enforced by the semantic pass

### Names and scopes

1. **Declaration before use.** A name is looked up from the innermost block outwards; it must be declared above
   its use. — follows: `assignment_identifier`; breaks: `sem_unknown_variable`.
2. **One declaration per scope.** A name is declared at most once per block; an inner block may declare the same
   name again and hides the outer one until the block ends. The parameters of a function and the top block of its
   body are one scope. — follows: `scope_shadowing_blocks`; breaks: `sem_redeclared_in_scope`.
3. **What a function body sees.** Its parameters, its own locals, the global variables (top-level variables
   outside any block) declared **above** the function, every function and every structure. It does not see
   globals declared below it nor variables of top-level `🤔` blocks. — follows: `func_sees_globals_above`;
   breaks: `sem_global_declared_below`.
4. **Name lookup inside a member function.** A name is looked up among the parameters and locals, then the fields
   of the object, then the globals declared above the structure. A call `f(…)` is looked up among the member
   functions of the structure, then the functions, then the structures (a constructor). So a parameter hides a field,
   and a field hides a global. — follows: `member_name_lookup`; breaks: `sem_member_lookup_param_first`
   (the assignment hits the parameter `x`, not the field `x`).
5. **Calls between functions.** A function may call itself and any function declared above or below it; a
   function name is declared once and may not be the name of a structure. — follows:
   `func_declared_below_nested_args`, `func_mutual_recursion`; breaks: `sem_unknown_function`,
   `sem_duplicate_function`.

### Mutability

6. **Modifiers.** `🙂` may be assigned any time. `☹️` gets its value in the declaration and is never assigned
   again. `🚫` gets its value in the declaration from a constant expression: literals, operators and other `🚫`
   constants. — follows: `constants_and_immutables`; breaks: `sem_assign_to_immutable`, `sem_assign_to_constant`,
   `sem_immutable_without_value`, `sem_constant_from_variable`.
7. **Parameters are read-only.** — breaks: `sem_assign_to_parameter`.
8. **Assignment through a chain.** `a.b.c => v` and `📖(a.b.c)` need every step mutable: the variable `a` is `🙂`
   and the fields `b` and `c` are `🙂`. — follows: `struct_field_chain`; breaks:
   `sem_assign_through_constant_chain`, `sem_assign_field_of_immutable_object`, `sem_assign_constant_field_in_member`.
9. **Mutating member functions.** A member function is *mutating* when it assigns (or reads into) a field of its
   object, or calls a mutating member function on its object or on a field of it (found by a fixed-point pass,
   so the call order of member functions does not matter). A mutating member function may be called only on an
   object that is mutable at every step of its chain — not on a `☹️`/`🚫` object, a parameter, an immutable
   field or a temporary like `Point(1, 2).shift(3)`. A non-mutating one may be called on any object. — follows:
   `member_mutating_calls`, `member_chains_and_objects`; breaks: `sem_mutating_on_constant_object`,
   `sem_mutating_through_constant_field`, `sem_mutating_indirect`, `sem_mutating_on_temporary`.

### Types

10. **Types** are `🐒` (i32), `🦍` (i64), `boo!👻` (bool) and structures. `➕ ➖ ✖️` take integers. `✅ ❎`
    compare two integers or two bools and give a bool; objects are not compared. — breaks: `sem_arith_on_bool`,
    `sem_compare_int_bool`, `sem_compare_objects`, `sem_bool_to_int`.
11. **Integer widths.** Arithmetic is done in the wider operand type (i64 if one side is i64). An i32 value
    widens to i64 silently. An i64 value may be stored into an i32 place (variable, field, parameter, result); it is
    range-checked at run time. — follows: `int_widths_and_arith`; breaks: `runtime_narrowing_error`.
12. **Conditions** of `🤔` are bool. — breaks: `sem_condition_not_bool`, `syn_if_integer_condition`.
13. **Arguments.** A call passes exactly as many arguments as the function has parameters; each one has the
    parameter's type (or a type that converts to it by rule 11). — follows: `func_declared_below_nested_args`;
    breaks: `sem_too_many_args`, `sem_too_few_args`, `sem_wrong_arg_type`.
14. **Result.** The value after every `🔙` has the result type of the function (or converts to it by rule 11).
    Every path through the body leaves it with `🔙` (or ends the program with `🚪`): the body counts as leaving when
    it contains a `🔙` / `🚪` statement, or an `🤔` with an `🤨` whose both blocks leave. — follows:
    `func_factorial_recursion`, `func_early_return`; breaks: `sem_wrong_return_type`,
    `sem_return_wrong_type_in_branch`, `sem_function_without_return`, `sem_return_missing_on_one_path`.
15. **Objects.** A constructor gets one value per field without `=> value`, in order, each of the field's type. A
    `🚫` field must have a `=> value`; a field's `=> value` is built from literals and operators. A variable of a
    structure type must be created with a value. A field may have a structure type only if that structure is
    declared above. — follows: `struct_constructor_defaults`; breaks: `sem_constructor_wrong_count`,
    `sem_constructor_wrong_type`, `sem_object_without_value`, `sem_constant_field_without_value`,
    `sem_struct_field_type_below`.
16. **Field access.** `obj.f` needs `obj` to be an object whose structure has the field `f`; `obj.m()` needs the
    member function `m`. — follows: `struct_field_chain`; breaks: `sem_unknown_field`,
    `sem_unknown_member_function`, `sem_field_of_non_struct`.

### Overflow checks

17. **Literals.** An integer literal must fit the type it takes: the expected type when it is the whole value
    (declaration, assignment, argument, result, constructor value), the type of the other operand when it is an
    operand, otherwise i32 if it fits, else i64. A literal that does not fit is a compilation error. — follows:
    `int_widths_and_arith` (2147483647 in i32), `print_every_kind` (9223372036854775807); breaks:
    `sem_literal_beyond_i32_still_parses`, `sem_i64_literal_overflow`, `sem_literal_operand_overflow`.
18. **Arithmetic.** A `➕ ➖ ✖️` whose result does not fit its type stops the program with
    `runtime error: line L:C: integer overflow in '➕' (i32)` on stderr and exit code 1. — follows:
    `int_widths_and_arith`; breaks: `runtime_overflow_add`.

### Input and output

19. **print.** `🖨️(v)` prints one value and then a newline: an integer in decimal (`%d` for i32, `%lld` for i64),
    a bool as `true` / `false`, a string literal as written (escapes decoded), an object as its structure name and
    its fields in declaration order: `Circle{center: Point{x: 1, y: 2}, radius: 5}` — nested objects inline, one
    newline after the whole object. — follows: `print_every_kind`, `struct_field_chain`; breaks:
    `syn_string_outside_print`, `syn_print_without_parens`.
20. **read.** `📖(target)` reads one integer from standard input into a mutable integer variable or field chain
    (rule 8). Input that is not an integer stops the program with a runtime error. — follows: `read_point`,
    `read_i32_and_i64`; breaks: `sem_read_into_bool`, `sem_read_into_immutable`, `syn_read_into_call`.
21. **exit.** `🚪 name` takes an integer or bool variable, prints `Program exit with result V` and ends the
    program with exit status V (bool: 1 / 0), also from inside a function. — follows: `exit_inside_function`,
    `full_program`; breaks: `sem_exit_object`.

### Syntax rules of the new constructs

- Functions and structures are declared only at the top level; member functions only inside a structure. —
  breaks: `syn_function_inside_block`, `syn_member_function_outside_struct`.
- `🔙 value` is used only inside a function body (at any depth). — follows: `func_early_return`; breaks:
  `syn_return_outside_function`.
- A structure has at least one field. — breaks: `syn_struct_without_fields`.
- The result of a call cannot be assigned to, nor can a field of it. — breaks: `syn_assign_to_call_result`.

## Build and run

Requirements: Python 3.8+, `llvmlite` (in the `~/lcd` virtual environment) and LLVM (`lli`, or `llc` and `clang`).

```
source ~/lcd/bin/activate
python3 compiler.py input.txt output.ll      # compile: writes the module the builder printed
lli output.ll                                # run it ...
llc -filetype=obj -relocation-model=pic output.ll -o output.o && clang output.o -o program && ./program   # ... or build a binary
python3 compiler.py --ast input.txt          # print the AST (front end only, no semantic pass)
```

A program that reads input takes it from standard input: `lli output.ll < input.in`.

`task2compiler.py` is the Task 2 front end alone (lexer + parser + AST, no `llvmlite` needed):
`python3 task2compiler.py --ast input.txt`. `test.txt` is a program using every new construct and `test.expected`
is its AST: `python3 task2compiler.py --ast test.txt | diff - test.expected`.

### Output of `--ast`

The AST indented by depth. Each node shows its position (`@line:column`, columns counted in characters) and its
fields: modifiers and mutability of variables and fields, parameter and result types of functions, the number of
arguments of a call, and for a chain its path and whether it ends in a member call:

```
FunctionNode @1:1 (name: add, result: i32, params: 2)
  ParamNode @1:10 (type: i32, name: a)
  ParamNode @1:15 (type: i32, name: b)
  Body
    ReturnNode @3:3
      BinOpNode @3:7 (op: +)
        ValueNode @3:5 (ID: a)
        ValueNode @3:9 (ID: b)
PrintNode @5:1
  ChainNode @5:4 (path: p.d2(), ends in member call: true)
    ValueNode @5:4 (ID: p)
    MemberCallStepNode @5:6 (member function: d2, args: 0)
```

### Errors

Any lexical, syntax or semantic error is one line on stderr, a non-zero exit code, nothing on stdout and no output
file:

```
compilation error: line 5:11: Argument 2 ('b') of function 'add' must be i32, got bool
```

Runtime errors (arithmetic overflow, an i64 that does not fit an i32, input that is not an integer) print
`runtime error: line L:C: …` on stderr and exit with code 1.

## How the compiler works

1. **Lexer** (`Lexer`): a byte-level state machine. Keywords and emojis are matched by one automaton (a trie over
   UTF-8 bytes, longest match); numbers, identifiers and string literals have their own states.
2. **Parser** (`Parser`): recursive descent, one method per grammar rule, one token of lookahead plus one extra
   token where a structure name may start a declaration (`🙂 Point p`). Every syntax error carries the position
   of the token that broke the rule.
3. **Semantic pass** (`Analyzer`), a separate pass before code generation, with a symbol table of
   - variables (`VarInfo`: type, modifier, global / local / parameter) in nested scopes,
   - functions (`FuncInfo`: parameter types, result type),
   - structures (`StructInfo`: fields in order with index, type and mutability; member functions with their
     signatures and whether they are mutating — a fixed point over the "calls a mutating member" relation).
   It annotates the AST (types, resolved names, field indexes) for the code generator.
4. **Code generation** (`CodeGen`) with the `llvmlite.ir` builder; the only IR text written is `str(module)`:
   - every Stage 1 construct: globals for top-level variables, `alloca`s for locals, `if`/`else` as basic blocks
     and a conditional branch, i32/i64/i1 with `sext` / checked `trunc`, arithmetic through
     `llvm.s{add,sub,mul}.with.overflow` with a branch to the runtime error;
   - one IR function per function, named `fn_<name>`, so `main` or `printf` in a program cannot clash with the
     runtime; all functions are declared before any body is generated;
   - one identified struct type per structure (`%struct.Point`); an object is an `alloca` of it; a field is a
     `getelementptr` by the index from the symbol table;
   - one IR function per member function, named `<Structure>.<name>`, whose first parameter is a pointer to the
     object; a call passes the object's address (a temporary is stored to a slot first);
   - `printf`, `scanf` (and `exit`, `fflush`, `dprintf` for the runtime) are declared without a body and linked
     from the C library; format strings are private global constants; printing an object walks the structure's
     field table with one `gep`, `load` and `printf` per field.

## Tests

```
source ~/lcd/bin/activate
python3 run_tests.py              # run every .ll with lli
python3 run_tests.py --native     # build every .ll with llc + clang and run the binary
python3 run_tests.py member read  # only the tests whose name contains 'member' or 'read'
python3 run_tests.py --update-ast # rewrite the .ast files of valid tests after a deliberate AST change
```

- `tests/valid/NAME.txt` — a program that compiles and runs (end to end). The script
  1. compares `--ast` with `NAME.ast` (and creates `NAME.ast` when it is missing),
  2. compiles the program to `build/valid/NAME.ll`,
  3. runs it with `NAME.in` as standard input when that file exists,
  4. compares what it prints (stdout, then stderr) with `NAME.expected`.
- `tests/errors/NAME.txt` — a program that must be rejected: stderr must equal `NAME.expected`, the exit code is
  non-zero, stdout is empty and no `.ll` file is written. When `NAME.ast` exists (all `sem_` tests), the program
  must still parse and print that AST: the error is found by the semantic pass.

The script prints `ok` / `FAIL` for every test, lists the failed ones at the end and exits non-zero if any fails.
Generated files go to `build/`, which is not committed.

| Folder | Count | Content |
|--------|-------|---------|
| `tests/valid` | 49 | the 30 valid Stage 1 programs (now also compiled and run) and 19 Stage 2 programs; 2 of them read input (`read_point`, `read_i32_and_i64`) |
| `tests/errors` | 96 | `lex_` lexical, `syn_` syntax, `sem_` semantic errors: 40 from Stage 1 (with the moved literal test), 56 new |

The Stage 1 test `literal_beyond_i32_still_parses` is now `tests/errors/sem_literal_beyond_i32_still_parses`: it
still parses (its `.ast` is the Stage 1 AST) and the semantic pass rejects the out-of-range i32 literal.

## Project layout

```
compiler.py        lexer, parser, AST, semantic pass, LLVM IR generation, command line
task2compiler.py   the Task 2 front end alone (lexer, parser, --ast)
grammar.ebnf       the grammar
README_TASK1.md    the Stage 2 constructs and the semantic rules
run_tests.py       test runner
tests/             valid/ and errors/ test cases
test.txt           Task 2 sample program, test.expected its AST
```
