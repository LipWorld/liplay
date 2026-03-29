# ============================================================
# lip_lang.py - 语法定义与解析器
# ============================================================
"""Lip language parser using Lark."""

from dataclasses import dataclass
from typing import Any

from lark import Lark, Transformer, v_args

# ============================================================
# AST Node Definitions
# ============================================================


@dataclass
class Program:
    stmts: list


@dataclass
class Assign:
    name: str
    typename: str | None
    value: Any


@dataclass
class Pipeline:
    head: Any
    steps: list


@dataclass
class PipeCap:
    name: str


@dataclass
class FuncCallRHS:
    name: str
    pos_args: list
    kw_args: dict


@dataclass
class MethodCallRHS:
    name: str
    pos_args: list
    kw_args: dict


@dataclass
class MethodAttrRHS:
    name: str


@dataclass
class TableRHS:
    table: Any


@dataclass
class BlockRHS:
    block: Any


@dataclass
class NameRHS:
    name: str


@dataclass
class Atom:
    base: Any
    accessors: list


@dataclass
class IdxAcc:
    index: Any


@dataclass
class DotAcc:
    name: str


@dataclass
class IntLit:
    value: int


@dataclass
class FloatLit:
    value: float


@dataclass
class BoolLit:
    value: bool


@dataclass
class StringLit:
    value: str


@dataclass
class PendingLit:
    pass


@dataclass
class TypeNameAtom:
    name: str


@dataclass
class NameAtom:
    name: str


@dataclass
class TableLit:
    seq: list
    named: dict


@dataclass
class BlockLit:
    params: list
    body: Any


@dataclass
class NamedArg:
    name: str
    value: Any


@dataclass
class DirectCall:
    name: str
    pos_args: list
    kw_args: dict


# ============================================================
# Grammar Definition
# ============================================================

GRAMMAR = r"""
start: stmt*

?stmt: (typed_assign | assign | expr_stmt) ";"?

typed_assign: NAME ":" TYPENAME "=" expr
assign: NAME ":" expr
expr_stmt: expr

?expr: pipeline

pipeline: atom (pipe_step | cap_step)*
pipe_step: "->" rhs
cap_step: ":>" NAME

?rhs: func_call_rhs
    | method_call_rhs
    | method_attr_rhs
    | table_rhs
    | block_rhs
    | name_rhs

func_call_rhs: NAME "(" arg_list? ")"
method_call_rhs: "." NAME "(" arg_list? ")"
method_attr_rhs: "." NAME
table_rhs: table_lit
block_rhs: block_lit
name_rhs: NAME

arg_list: arg ("," arg)*
?arg: named_arg | pos_arg
named_arg: NAME ":" expr  -> named_arg
pos_arg: expr             -> pos_arg

atom: primary accessor*
?accessor: idx_acc | dot_acc
idx_acc: "[" expr "]"
dot_acc: "." NAME

?primary: float_lit
        | int_lit
        | bool_lit
        | pending_lit
        | string_lit
        | typename_atom
        | direct_call
        | name_atom
        | table_lit
        | block_lit
        | paren

direct_call: NAME "(" arg_list? ")"

float_lit: SIGNED_FLOAT
int_lit: SIGNED_INT
bool_lit: BOOL
pending_lit: "?"
string_lit: ESCAPED_STRING
typename_atom: TYPENAME
name_atom: NAME

paren: "(" expr ")"

table_lit: "[" table_body? "]"
table_body: table_item ("," table_item)* ","?
?table_item: named_item | pos_item
named_item: NAME ":" expr  -> named_item
pos_item: expr             -> pos_item

block_lit: "{" param_list ":" expr "}"
param_list: (NAME ("," NAME)*)?

TYPENAME.2: "Int" | "Float" | "Bool" | "String" | "Block" | "Table"
BOOL.2: "true" | "false"
NAME: /[a-zA-Z_][a-zA-Z0-9_]*/

SIGNED_FLOAT: /-?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?/
SIGNED_INT: /-?\d+/

%import common.ESCAPED_STRING
%import common.WS
%import common.SH_COMMENT

%ignore WS
%ignore SH_COMMENT
%ignore /--[^\n]*/
"""

# ============================================================
# AST Transformer
# ============================================================


class LipTransformer(Transformer):
    def start(self, items):
        return Program(list(items))

    def typed_assign(self, items):
        name, typename, value = items
        return Assign(str(name), str(typename), value)

    def assign(self, items):
        name, value = items
        return Assign(str(name), None, value)

    def expr_stmt(self, items):
        return items[0]

    def pipeline(self, items):
        if len(items) == 1:
            return items[0]
        head = items[0]
        steps = list(items[1:])
        return Pipeline(head, steps)

    def pipe_step(self, items):
        return items[0]

    def cap_step(self, items):
        return PipeCap(str(items[0]))

    def func_call_rhs(self, items):
        name = str(items[0])
        pos_args, kw_args = [], {}
        if len(items) > 1 and items[1]:
            pos_args, kw_args = items[1]
        return FuncCallRHS(name, pos_args, kw_args)

    def method_call_rhs(self, items):
        name = str(items[0])
        pos_args, kw_args = [], {}
        if len(items) > 1 and items[1]:
            pos_args, kw_args = items[1]
        return MethodCallRHS(name, pos_args, kw_args)

    def method_attr_rhs(self, items):
        return MethodAttrRHS(str(items[0]))

    def table_rhs(self, items):
        return TableRHS(items[0])

    def block_rhs(self, items):
        return BlockRHS(items[0])

    def name_rhs(self, items):
        return NameRHS(str(items[0]))

    def arg_list(self, items):
        pos_args, kw_args = [], {}
        for item in items:
            if isinstance(item, NamedArg):
                kw_args[item.name] = item.value
            else:
                pos_args.append(item)
        return (pos_args, kw_args)

    def named_arg(self, items):
        return NamedArg(str(items[0]), items[1])

    def pos_arg(self, items):
        return items[0]

    def atom(self, items):
        if len(items) == 1:
            return items[0]
        base = items[0]
        accessors = list(items[1:])
        return Atom(base, accessors)

    def idx_acc(self, items):
        return IdxAcc(items[0])

    def dot_acc(self, items):
        return DotAcc(str(items[0]))

    def direct_call(self, items):
        name = str(items[0])
        pos_args, kw_args = [], {}
        if len(items) > 1 and items[1]:
            pos_args, kw_args = items[1]
        return DirectCall(name, pos_args, kw_args)

    def float_lit(self, items):
        return FloatLit(float(items[0]))

    def int_lit(self, items):
        return IntLit(int(items[0]))

    def bool_lit(self, items):
        return BoolLit(str(items[0]) == "true")

    def pending_lit(self, items):
        return PendingLit()

    def string_lit(self, items):
        s = str(items[0])
        s = s[1:-1]
        s = s.replace("\\n", "\n").replace("\\t", "\t")
        s = s.replace('\\"', '"').replace("\\\\", "\\")
        return StringLit(s)

    def typename_atom(self, items):
        return TypeNameAtom(str(items[0]))

    def name_atom(self, items):
        return NameAtom(str(items[0]))

    def paren(self, items):
        return items[0]

    def table_lit(self, items):
        seq, named = [], {}
        if items:
            for item in items[0]:
                if isinstance(item, tuple):
                    named[item[0]] = item[1]
                else:
                    seq.append(item)
        return TableLit(seq, named)

    def table_body(self, items):
        return list(items)

    def named_item(self, items):
        return (str(items[0]), items[1])

    def pos_item(self, items):
        return items[0]

    def block_lit(self, items):
        params = items[0] if items[0] else []
        body = items[1]
        return BlockLit(params, body)

    def param_list(self, items):
        return [str(t) for t in items]


# ============================================================
# Parser Interface
# ============================================================

_parser = None


def get_parser():
    global _parser
    if _parser is None:
        _parser = Lark(GRAMMAR, parser="lalr", transformer=LipTransformer())
    return _parser


def parse(source: str) -> Program:
    return get_parser().parse(source)
