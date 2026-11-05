# Emoji language — Stage 3 (encapsulation, optimizer)

A small statically-typed language written with emojis. The compiler is a hand-written byte-level lexer (a state
machine), a recursive-descent parser (one function per grammar rule), a semantic pass with a symbol table, and an
LLVM IR generator built with the `llvmlite.ir` builder. Compiled programs run with `lli` or `llc` + `clang`.

- [`grammar.ebnf`](grammar.ebnf) — the full grammar with its lexical rules

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
    newline after the whole object; private fields are left out by Stage 3 rule 5. — follows: `print_every_kind`, `struct_field_chain`; breaks:
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

## The language — Stage 3 feature: encapsulation

`🔓` (public) and `🔒` (private) go in front of a field or a member function of a structure. They are checked by
the semantic pass and are gone by code generation: a private field has the same layout and the same `gep` as a
public one.

### Rules

1. **Default.** A field or member function without a modifier is **public**; nothing is private by default. `🔓`
   only says so explicitly. — follows: `encapsulation_public_by_default`.
2. **Where a private member is reachable.** A private field or member function is used only inside the member
   functions of its own structure: by plain name (`pin`, `secret()`), or on another object of the same structure
   (`o.x`, `o.sum()`). — follows: `encapsulation_private_member_function`,
   `encapsulation_same_structure_objects`, `encapsulation_read_into_private`.
3. **Access from outside is an error that names the member.** Reading, assigning (`v.pin => 2`), reading input into
   it (`📖(v.pin)`) or calling it from the top level, from a function or from a member function of another structure
   gives `Cannot access private field 'pin' of structure 'Vault' from outside it` or
   `Cannot call private member function 'secret' of structure 'Vault' from outside it`, at the position of the
   member's name. A private step in the middle of a chain counts too (`o.in.x`). — breaks:
   `encapsulation_read_private_field`, `encapsulation_assign_private_field`, `encapsulation_call_private_member`,
   `encapsulation_read_into_private_field`, `encapsulation_from_plain_function`,
   `encapsulation_from_other_structure`, `encapsulation_member_call_from_other_structure`,
   `encapsulation_private_step_in_chain`.
4. **Constructors set private fields.** `Name(…)` takes a value for every field without `=> value`, private ones
   included, from anywhere in the program; missing one is still an error. — follows:
   `encapsulation_private_field_getter`; breaks: `encapsulation_constructor_needs_private_value`.
5. **Printing does not reveal private fields.** `🖨️(obj)` shows a private field only when it runs inside a member
   function of that field's structure; elsewhere the field is left out: `Card{owner: 7, key: Key{}}`. — follows:
   `encapsulation_print_hides_private`, `encapsulation_private_object_field`.
6. **Modifiers go on members only**, at most one per member. — breaks: `encapsulation_two_modifiers`,
   `encapsulation_on_variable`, `encapsulation_on_function`, `encapsulation_before_statement_in_struct`.

All other rules are unchanged: a private field still follows its mutability modifier, and a private mutating member
function still makes its callers mutating.

### Example 1: a private field behind a getter

```
🏰 Account
{
  🔒 🙂 🦍 balance
  ☹️ 🐒 id
  🛠️ 🦍 getBalance()
  {
    🔙 balance
  }
}
☹️ Account acc => Account(100, 7)
🖨️(acc.getBalance())
🖨️(acc)
```

prints `100` and `Account{id: 7}`. Writing `🖨️(acc.balance)` instead is
`compilation error: line 11:8: Cannot access private field 'balance' of structure 'Account' from outside it`.

### Example 2: a private member function

```
🏰 Counter
{
  🔒 🙂 🐒 value
  🔒 🛠️ 🐒 step()
  {
    🔙 2
  }
  🔒 🛠️ 🐒 bump()
  {
    value => value ➕ step()
    🔙 value
  }
  🔓 🛠️ 🐒 tick()
  {
    bump()
    🔙 bump()
  }
}
🙂 Counter c => Counter(1)
🖨️(c.tick())
```

prints `5`.

### The IR of Example 1

```llvm
define i64 @"Account.getBalance"(%"struct.Account"* %"this")
{
entry:
  %"balance" = getelementptr inbounds %"struct.Account", %"struct.Account"* %"this", i32 0, i32 0
  %"balance.1" = load i64, i64* %"balance"
  ret i64 %"balance.1"
...
define i32 @"main"()
...
  %"balance" = getelementptr inbounds %"struct.Account", %"struct.Account"* %"new.Account", i32 0, i32 0
  store i64 100, i64* %"balance"
...
  %".8" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([9 x i8], [9 x i8]* @"str.2", i32 0, i32 0))
  %"id.1" = getelementptr inbounds %"struct.Account", %"struct.Account"* @"g.acc", i32 0, i32 1
  %".9" = load i32, i32* %"id.1"
  %".10" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([7 x i8], [7 x i8]* @"str.3", i32 0, i32 0), i32 %".9")
```

`Account.getBalance` reaches the private `balance` with an ordinary `getelementptr` at index 0 of its `this`
pointer: privacy costs nothing at run time, because the check already happened in the semantic pass. The constructor
in `main` writes the same index directly, which is why a private field can be set when the object is created. The
print of `acc` emits `Account{` and then one `gep`, `load` and `printf` for `id` at index 1 only: index 0 is skipped,
so the private balance never reaches `printf`.

## The optimizer (`--optimize`)

`--optimize`, anywhere on the command line, runs three transformations of the checked tree before code generation.
They repeat until none of them finds anything, because each one opens work for the others. With `--ast` the
program is also checked, and the tree after the optimizer is printed. Errors are the same with and without the flag.

### Unused variables

- A variable is removed, with all its assignments, when nothing reads it. This repeats: removing `c => b` can leave
  `b` unread. Variables are matched by their declaration, not their name, so a shadowing variable and the one it
  hides are decided separately (`unused_var_chain`, `unused_var_shadowing`).
- A write to a field of an object is an assignment to that object (`p.x => 3`, `unused_var_object`). `📖(x)`
  and a member call on an object count as reads, so they stay.
- An expression that calls a function is never dropped. `🙂 🐒 a => f(1)` becomes the call statement `f(1)`. A
  bigger expression such as `f(1) ➕ 1` keeps its variable (`unused_var_keeps_calls_and_read`).
- **An expression that can stop the program also stays.** `big ➕ 1` can end in the overflow error and an i64 stored
  into an i32 can end in the range error, so removing them could change what the program prints. Arithmetic is
  dropped only when it is built from literals and `🚫` constants and does not overflow. If one statement of a
  variable has to stay, the whole variable stays.

### Unused functions

A function is kept only if the top-level code reaches it through calls. So a body that goes away takes the functions
only it called, and two functions that call only each other are removed too (`unused_fn_chain`). This covers member
functions as well; the fields of a structure never change (`unused_fn_member`).

### Inlining

A function called exactly once is replaced at its call. Each parameter becomes a `☹️` local initialised with the
argument, the rest of the body follows, and the value of its `🔙` stands where the call stood. If that value has
another type than the function's result, a local of the result type holds it, so the conversion still happens. A call
used as a statement leaves a `name$N$result` local, which the unused-variable pass then removes or reduces. Locals
are renamed `function$N$name`: `$` cannot be in a source name, so nothing can collide. The function is then removed
as unused (`inline_simple`, `inline_renames_locals`, `inline_nested_calls`, `inline_statement_condition_result`).

**Inlined:** a plain function that is called once and has exactly one `🔙`, as the last statement of its body. The
body may hold anything else, including `🤔` blocks and `🚪`.

**Left alone** (`inline_left_alone`, `inline_keeps_evaluation_order`):

- a recursive function, directly or through other functions;
- a body with a `🔙` inside a block, such as an early return in an `🤔`: there is no single value to put at the call;
- a member function: it needs its object;
- a call that cannot move. The body runs before the statement that held the call, so everything evaluated earlier in
  that statement must not notice. In `counter ➕ bump()` the global `counter` would be read after `bump` changed it.
  In `show(1) ➕ second()` the prints would swap. In `a ✖️ b ➕ f()` the `✖️` could overflow first. Literals, locals and
  parameters may stand before the call; globals, fields, calls and arithmetic may not.

### Before and after

`tests/optimizer/inline_simple` is `🙂 🐒 total => add(2, 3)` with `add` returning `a ➕ b`. Without `--optimize`,
`main` calls the function:

```llvm
define i32 @"fn_add"(i32 %"a", i32 %"b")
{
entry:
  %"b.addr" = alloca i32
  %"a.addr" = alloca i32
  store i32 %"a", i32* %"a.addr"
  store i32 %"b", i32* %"b.addr"
  ...
  ret i32 %".11"
}

define i32 @"main"()
{
entry:
  %".2" = call i32 @"fn_add"(i32 2, i32 3)
  store i32 %".2", i32* @"g.total"
```

With `--optimize`, `@fn_add` is gone, the parameters are locals of `main`, and the addition is done in place:

```llvm
define i32 @"main"()
{
entry:
  %"add$1$b" = alloca i32
  %"add$1$a" = alloca i32
  store i32 2, i32* %"add$1$a"
  store i32 3, i32* %"add$1$b"
  %"add$1$a.1" = load i32, i32* %"add$1$a"
  %"add$1$b.1" = load i32, i32* %"add$1$b"
  %".4" = call {i32, i1} @"llvm.sadd.with.overflow.i32"(i32 %"add$1$a.1", i32 %"add$1$b.1")
  ...
  %".9" = extractvalue {i32, i1} %".4", 0
  store i32 %".9", i32* @"g.total"
```

The overflow check moved with the body and still reports the position inside `add`. The module goes from 61 to 52
lines.

## Build and run

Requirements: Python 3.8+, `llvmlite` (in the `~/lcd` virtual environment) and LLVM (`lli`, or `llc` and `clang`).

```
source ~/lcd/bin/activate
python3 compiler.py input.txt output.ll      # compile: writes the module the builder printed
lli output.ll                                # run it ...
llc -filetype=obj -relocation-model=pic output.ll -o output.o && clang output.o -o program && ./program   # ... or build a binary
python3 compiler.py --ast input.txt          # print the AST (front end only, no semantic pass)
python3 compiler.py --optimize input.txt output.ll   # compile through the optimizer
python3 compiler.py --optimize --ast input.txt       # check, optimize and print the tree
```

A program that reads input takes it from standard input: `lli output.ll < input.in`.

### Output of `--ast`

The AST indented by depth. Each node shows its position (`@line:column`, columns counted in characters) and its
fields: modifiers and mutability of variables and fields, parameter and result types of functions, the number of
arguments of a call, for a chain its path and whether it ends in a member call, and `access: public` / `access: private`
on a member that has `🔓` / `🔒` written:

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
     signatures and whether they are mutating — a fixed point over the "calls a mutating member" relation; each
     field and member function also records whether it is private).
   It annotates the AST (types, resolved names, field indexes) for the code generator.
4. **Optimizer** (`Optimizer`, only with `--optimize`): tree transformations between the semantic pass and code
   generation. It removes unused functions and variables and inlines functions called once.
5. **Code generation** (`CodeGen`) with the `llvmlite.ir` builder; the only IR text written is `str(module)`:
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
python3 run_tests.py --optimize   # the same tests compiled through the optimizer
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

- `tests/optimizer/NAME.txt` — a program that shows one transformation. It must print `NAME.expected` in both
  modes below, and `NAME.in` is its input when it exists. With `--optimize`, `--optimize --ast` must also equal
  `NAME.ast`.

`python3 run_tests.py` never uses the optimizer. `python3 run_tests.py --optimize` compiles every test in all three
folders through it, against the same expected files, so passing in both modes shows the optimizer changes no
output and no error. `--optimize` goes after `run_tests.py`: placed before it, the flag would go to `python3`.
`--native`, `--optimize` and name filters can be combined.

The script prints `ok` / `FAIL` for every test, lists the failed ones at the end and exits non-zero if any fails.
Generated files go to `build/`, which is not committed.

| Folder | Count | Content |
|--------|-------|---------|
| `tests/valid` | 56 | the 30 valid Stage 1 programs (now also compiled and run), 19 Stage 2 programs and 7 `encapsulation_` programs; 3 of them read input (`read_point`, `read_i32_and_i64`, `encapsulation_read_into_private`) |
| `tests/errors` | 109 | `lex_` lexical, `syn_` syntax, `sem_` semantic errors: 40 from Stage 1 (with the moved literal test), 56 from Stage 2, and 13 `encapsulation_` errors |
| `tests/optimizer` | 12 | `unused_var_` (4), `unused_fn_` (2) and `inline_` (6) programs with the tree after `--optimize` |

The Stage 1 test `literal_beyond_i32_still_parses` is now `tests/errors/sem_literal_beyond_i32_still_parses`: it
still parses (its `.ast` is the Stage 1 AST) and the semantic pass rejects the out-of-range i32 literal.

## Project layout

```
compiler.py        lexer, parser, AST, semantic pass, optimizer, LLVM IR generation, command line
grammar.ebnf       the grammar
run_tests.py       test runner
tests/             valid/, errors/ and optimizer/ test cases
```
