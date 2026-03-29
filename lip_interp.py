# ============================================================
# lip_interp.py - 解释器与内置函数
# ============================================================
"""Lip language interpreter."""

import math
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from lip_lang import (
    Assign,
    Atom,
    BlockLit,
    BlockRHS,
    BoolLit,
    DirectCall,
    DotAcc,
    FloatLit,
    FuncCallRHS,
    IdxAcc,
    IntLit,
    MethodAttrRHS,
    MethodCallRHS,
    NameAtom,
    NameRHS,
    PendingLit,
    PipeCap,
    Pipeline,
    Program,
    StringLit,
    TableLit,
    TableRHS,
    TypeNameAtom,
)

# ============================================================
# Runtime Values
# ============================================================


@dataclass
class Pending:
    """Represents a pending/unknown value with trace information."""

    file: str = "<unknown>"
    line: int = 0
    operation: str = ""
    reason: str = "unknown"
    chain: list = field(default_factory=list)

    def extend(self, op: str) -> "Pending":
        """Create a new Pending with an extended chain."""
        return Pending(
            file=self.file,
            line=self.line,
            operation=self.operation,
            reason=self.reason,
            chain=self.chain + [op],
        )


PENDING = Pending(reason="literal pending value")


def is_pending(val: Any) -> bool:
    return isinstance(val, Pending)


def make_pending(op: str, reason: str) -> Pending:
    return Pending(operation=op, reason=reason)


# ============================================================
# LipTable - Unified list/dict structure
# ============================================================


class LipTable:
    def __init__(self, seq: list = None, named: dict = None):
        self.seq = seq if seq is not None else []
        self.named = named if named is not None else {}

    def get(self, key: Any) -> Any:
        """Get value by key. For dispatch: true->0, false->1, pending->2"""
        if isinstance(key, int):
            if 0 <= key < len(self.seq):
                return self.seq[key]
            return make_pending("get", f"index {key} out of range")
        elif isinstance(key, str):
            if key in self.named:
                return self.named[key]
            return make_pending("get", f"key '{key}' not found")
        elif is_pending(key):
            if len(self.seq) > 2:
                return self.seq[2]
            return key
        return make_pending("get", f"invalid key type: {type(key).__name__}")

    def get_dispatch(self, val: Any) -> Any:
        """Three-way dispatch: true->0, false->1, pending->2"""
        if is_pending(val):
            idx = 2
        elif val is True:
            idx = 0
        elif val is False:
            idx = 1
        elif isinstance(val, int):
            idx = val
        elif isinstance(val, str):
            return self.get(val)
        else:
            idx = 0

        if 0 <= idx < len(self.seq):
            return self.seq[idx]
        return make_pending("dispatch", f"branch {idx} not found")

    def set(self, key: Any, val: Any) -> "LipTable":
        new_seq = self.seq.copy()
        new_named = self.named.copy()
        if isinstance(key, int):
            while len(new_seq) <= key:
                new_seq.append(PENDING)
            new_seq[key] = val
        elif isinstance(key, str):
            new_named[key] = val
        return LipTable(new_seq, new_named)

    def append(self, val: Any) -> "LipTable":
        return LipTable(self.seq + [val], self.named.copy())

    def merge(self, other: "LipTable") -> "LipTable":
        new_named = {**self.named, **other.named}
        return LipTable(self.seq + other.seq, new_named)

    def keys(self) -> list:
        return list(self.named.keys())

    def values(self) -> list:
        return list(self.named.values())

    def length(self) -> int:
        return len(self.seq)

    def total_length(self) -> int:
        return len(self.seq) + len(self.named)

    def __repr__(self):
        parts = [repr(v) for v in self.seq]
        parts += [f"{k}: {repr(v)}" for k, v in self.named.items()]
        return "[" + ", ".join(parts) + "]"


# ============================================================
# LipBlock - Closure/Function
# ============================================================


@dataclass
class LipBlock:
    params: list
    body: Any
    closure: "Env"

    def __repr__(self):
        params_str = ", ".join(self.params) if self.params else ""
        return f"{{ {params_str}: <body> }}"


# ============================================================
# Dispatch - For three-way branching
# ============================================================


@dataclass
class Dispatch:
    selected: Any
    original_value: Any


# ============================================================
# Environment
# ============================================================


class Env:
    def __init__(self, parent: "Env" = None):
        self.bindings: dict = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.bindings:
            return self.bindings[name]
        if self.parent:
            return self.parent.get(name)
        return None

    def set(self, name: str, val: Any):
        self.bindings[name] = val

    def child(self) -> "Env":
        return Env(self)


# ============================================================
# Interpreter
# ============================================================

PENDING_SAFE_FUNS = {"recover", "is", "on_pending", "not", "type"}


class Interpreter:
    def __init__(self):
        self.global_env = Env()
        self._register_builtins()
        self._register_types()

    def _register_types(self):
        for t in ["Int", "Float", "Bool", "String", "Block", "Table", "Pending"]:
            self.global_env.set(t, t)

    def _register_builtins(self):
        builtins = {
            # 数学运算
            "add": self._b_add,
            "sub": self._b_sub,
            "mul": self._b_mul,
            "div": self._b_div,
            "mod": self._b_mod,
            "pow": self._b_pow,
            "neg": self._b_neg,
            "abs": self._b_abs,
            "sqrt": self._b_sqrt,
            "floor": self._b_floor,
            "ceil": self._b_ceil,
            "round": self._b_round,
            "min": self._b_min,
            "max": self._b_max,
            # 比较运算
            "eq": self._b_eq,
            "ne": self._b_ne,
            "neq": self._b_ne,
            "lt": self._b_lt,
            "le": self._b_le,
            "gt": self._b_gt,
            "ge": self._b_ge,
            "gte": self._b_ge,
            "lte": self._b_le,
            # 逻辑运算
            "and": self._b_and,
            "or": self._b_or,
            "not": self._b_not,
            # 类型操作
            "is": self._b_is,
            "as": self._b_as,
            "type": self._b_type,
            # 字符串操作
            "upper": self._b_upper,
            "lower": self._b_lower,
            "trim": self._b_trim,
            "split": self._b_split,
            "join": self._b_join,
            "concat": self._b_concat,
            "replace": self._b_replace,
            "starts_with": self._b_starts_with,
            "ends_with": self._b_ends_with,
            "contains": self._b_contains,
            "slice": self._b_slice,
            # I/O
            "print": self._b_print,
            "log": self._b_log,
            "warn": self._b_warn,
            # 控制流
            "recover": self._b_recover,
            "on_pending": self._b_on_pending,
            "run": self._b_run,
            # 高阶函数
            "map": self._b_map,
            "filter": self._b_filter,
            "reduce": self._b_reduce,
            "each": self._b_each,
            "find": self._b_find,
            "every": self._b_every,
            "some": self._b_some,
            "flatmap": self._b_flatmap,
            # Table 操作
            "pairs": self._b_pairs,
            "range": self._b_range,
            "length": self._b_length,
            "len": self._b_length,
            "keys": self._b_keys,
            "values": self._b_values,
            "has": self._b_has,
            "get": self._b_get,
            "set": self._b_set,
            "append": self._b_append,
            "push": self._b_append,
            "first": self._b_first,
            "last": self._b_last,
            "take": self._b_take,
            "drop": self._b_drop,
            "reverse": self._b_reverse,
            "sort": self._b_sort,
            "sort_by": self._b_sort_by,
            "merge": self._b_merge,
            "flatten": self._b_flatten,
            "zip": self._b_zip,
            "sum": self._b_sum,
            "avg": self._b_avg,
            "spread": self._b_spread,
            "remove": self._b_remove,
        }
        for name, fn in builtins.items():
            self.global_env.set(name, fn)

    # ========== Evaluation ==========

    def eval(self, node: Any, env: Env = None) -> Any:
        if env is None:
            env = self.global_env

        if isinstance(node, Program):
            result = None
            for stmt in node.stmts:
                result = self.eval(stmt, env)
            return result

        elif isinstance(node, Assign):
            val = self.eval(node.value, env)
            env.set(node.name, val)
            return val

        elif isinstance(node, IntLit):
            return node.value

        elif isinstance(node, FloatLit):
            v = node.value
            if math.isnan(v) or math.isinf(v):
                return make_pending("float", "NaN or Inf")
            return v

        elif isinstance(node, BoolLit):
            return node.value

        elif isinstance(node, StringLit):
            return node.value

        elif isinstance(node, PendingLit):
            return PENDING

        elif isinstance(node, TypeNameAtom):
            return node.name

        elif isinstance(node, NameAtom):
            val = env.get(node.name)
            if val is None:
                return make_pending("lookup", f"undefined variable: {node.name}")
            return val

        elif isinstance(node, TableLit):
            seq = [self.eval(item, env) for item in node.seq]
            named = {k: self.eval(v, env) for k, v in node.named.items()}
            return LipTable(seq, named)

        elif isinstance(node, BlockLit):
            return LipBlock(node.params, node.body, env)

        elif isinstance(node, Atom):
            val = self.eval(node.base, env)
            for acc in node.accessors:
                val = self._apply_acc(val, acc, env)
            return val

        elif isinstance(node, DirectCall):
            fn = env.get(node.name)
            if fn is None:
                return make_pending("call", f"undefined function: {node.name}")
            pos_args = [self.eval(a, env) for a in node.pos_args]
            kw_args = {k: self.eval(v, env) for k, v in node.kw_args.items()}
            return self._call_value(fn, PENDING, pos_args, kw_args, env)

        elif isinstance(node, Pipeline):
            return self._eval_pipeline(node, env)

        else:
            raise RuntimeError(f"Unknown node type: {type(node)}")

    def _apply_acc(self, val: Any, acc: Any, env: Env) -> Any:
        if is_pending(val):
            return val

        if isinstance(acc, IdxAcc):
            idx = self.eval(acc.index, env)
            return self._do_index(val, idx)
        elif isinstance(acc, DotAcc):
            return self._get_attr(val, acc.name)
        return make_pending("accessor", f"unknown accessor: {type(acc)}")

    def _do_index(self, val: Any, idx: Any) -> Any:
        if isinstance(val, LipTable):
            return val.get(idx)
        elif isinstance(val, str):
            if isinstance(idx, int):
                if 0 <= idx < len(val):
                    return val[idx]
                return make_pending("index", "string index out of range")
        return make_pending("index", f"cannot index {type(val).__name__}")

    def _get_attr(self, val: Any, name: str) -> Any:
        if name == "__trace__":
            if is_pending(val):
                return LipTable(
                    [],
                    {
                        "file": val.file,
                        "line": val.line,
                        "operation": val.operation,
                        "reason": val.reason,
                        "chain": LipTable(val.chain),
                    },
                )
            return LipTable()

        if isinstance(val, LipTable):
            if name in val.named:
                return val.named[name]
            return make_pending("attr", f"attribute '{name}' not found")

        if isinstance(val, str):
            if name == "length":
                return len(val)

        return make_pending(
            "attr", f"cannot get attribute '{name}' from {type(val).__name__}"
        )

    def _eval_pipeline(self, node: Pipeline, env: Env) -> Any:
        val = self.eval(node.head, env)

        for step in node.steps:
            if isinstance(step, PipeCap):
                env.set(step.name, val)
            else:
                if is_pending(val) and not self._is_pending_safe(step):
                    val = val.extend(self._step_to_str(step))
                else:
                    val = self._apply_pipe(val, step, env)

        return val

    def _is_pending_safe(self, step: Any) -> bool:
        if isinstance(step, FuncCallRHS):
            return step.name in PENDING_SAFE_FUNS
        if isinstance(step, TableRHS):
            return True
        return False

    def _step_to_str(self, step: Any) -> str:
        if isinstance(step, FuncCallRHS):
            return f"{step.name}(...)"
        if isinstance(step, MethodCallRHS):
            return f".{step.name}(...)"
        if isinstance(step, MethodAttrRHS):
            return f".{step.name}"
        return str(type(step).__name__)

    def _apply_pipe(self, val: Any, step: Any, env: Env) -> Any:
        if isinstance(step, FuncCallRHS):
            fn = env.get(step.name)
            if fn is None:
                return make_pending("call", f"undefined function: {step.name}")
            pos_args = [self.eval(a, env) for a in step.pos_args]
            kw_args = {k: self.eval(v, env) for k, v in step.kw_args.items()}
            return self._call_value(fn, val, pos_args, kw_args, env)

        elif isinstance(step, MethodCallRHS):
            pos_args = [self.eval(a, env) for a in step.pos_args]
            kw_args = {k: self.eval(v, env) for k, v in step.kw_args.items()}
            return self._call_method(val, step.name, pos_args, kw_args, env)

        elif isinstance(step, MethodAttrRHS):
            return self._get_attr(val, step.name)

        elif isinstance(step, TableRHS):
            table = self.eval(step.table, env)
            if not isinstance(table, LipTable):
                return make_pending("dispatch", "expected table for dispatch")
            # 使用新的 get_dispatch 方法，正确处理 true->0, false->1, pending->2
            selected = table.get_dispatch(val)
            return Dispatch(selected, val)

        elif isinstance(step, BlockRHS):
            block = self.eval(step.block, env)
            return self._call_block(block, [val], {}, env)

        elif isinstance(step, NameRHS):
            fn = env.get(step.name)
            if fn is None:
                return make_pending("call", f"undefined: {step.name}")
            return self._call_value(fn, val, [], {}, env)

        return make_pending("pipe", f"unknown pipe step: {type(step)}")

    def _call_value(
        self, fn: Any, upstream: Any, pos_args: list, kw_args: dict, env: Env
    ) -> Any:
        if isinstance(fn, LipBlock):
            # 确定参数列表
            if upstream is PENDING:
                all_args = pos_args
            else:
                all_args = [upstream] + pos_args
            return self._call_block(fn, all_args, kw_args, env)
        elif callable(fn):
            return fn(upstream, pos_args, kw_args, env)
        return make_pending("call", f"not callable: {type(fn).__name__}")

    def _call_method(
        self, obj: Any, name: str, pos_args: list, kw_args: dict, env: Env
    ) -> Any:
        if isinstance(obj, LipTable) and name in obj.named:
            method = obj.named[name]
            if isinstance(method, LipBlock):
                return self._call_block(method, pos_args, kw_args, env)

        method_map = {
            "length": self._m_length,
            "len": self._m_length,
            "keys": self._m_keys,
            "values": self._m_values,
            "has": self._m_has,
            "get": self._m_get,
            "set": self._m_set,
            "append": self._m_append,
            "push": self._m_append,
            "merge": self._m_merge,
            "map": self._m_map,
            "filter": self._m_filter,
            "reduce": self._m_reduce,
            "each": self._m_each,
            "pairs": self._m_pairs,
            "take": self._m_take,
            "drop": self._m_drop,
            "first": self._m_first,
            "last": self._m_last,
            "reverse": self._m_reverse,
            "sort": self._m_sort,
            "sort_by": self._m_sort_by,
            "sum": self._m_sum,
            "avg": self._m_avg,
            "min": self._m_min,
            "max": self._m_max,
            "flatten": self._m_flatten,
            "zip": self._m_zip,
            "find": self._m_find,
            "every": self._m_every,
            "some": self._m_some,
            "contains": self._m_contains,
            "upper": self._m_upper,
            "lower": self._m_lower,
            "trim": self._m_trim,
            "split": self._m_split,
            "join": self._m_join,
            "concat": self._m_concat,
            "replace": self._m_replace,
            "starts_with": self._m_starts_with,
            "ends_with": self._m_ends_with,
            "slice": self._m_slice,
        }

        if name in method_map:
            return method_map[name](obj, pos_args, kw_args, env)

        return make_pending("method", f"unknown method: {name}")

    def _call_block(self, block: LipBlock, args: list, kw_args: dict, env: Env) -> Any:
        local = block.closure.child()
        for i, param in enumerate(block.params):
            if i < len(args):
                local.set(param, args[i])
            elif param in kw_args:
                local.set(param, kw_args[param])
            else:
                local.set(param, PENDING)
        return self.eval(block.body, local)

    # ========== Builtin Functions ==========

    def _b_add(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("add", "missing argument")
        b = args[0]
        if is_pending(b):
            return b
        if isinstance(up, str) or isinstance(b, str):
            return str(up) + str(b)
        try:
            return up + b
        except:
            return make_pending("add", "incompatible types")

    def _b_sub(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("sub", "missing argument")
        b = args[0]
        if is_pending(b):
            return b
        try:
            return up - b
        except:
            return make_pending("sub", "incompatible types")

    def _b_mul(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("mul", "missing argument")
        b = args[0]
        if is_pending(b):
            return b
        try:
            return up * b
        except:
            return make_pending("mul", "incompatible types")

    def _b_div(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("div", "missing argument")
        b = args[0]
        if is_pending(b):
            return b
        try:
            if b == 0:
                return make_pending("div", "division by zero")
            return up / b
        except:
            return make_pending("div", "incompatible types")

    def _b_mod(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("mod", "missing argument")
        b = args[0]
        if is_pending(b):
            return b
        try:
            if b == 0:
                return make_pending("mod", "modulo by zero")
            return up % b
        except:
            return make_pending("mod", "incompatible types")

    def _b_pow(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("pow", "missing argument")
        b = args[0]
        if is_pending(b):
            return b
        try:
            return up**b
        except:
            return make_pending("pow", "incompatible types")

    def _b_neg(self, up, args, kw, env):
        if is_pending(up):
            return up
        try:
            return -up
        except:
            return make_pending("neg", "cannot negate")

    def _b_abs(self, up, args, kw, env):
        if is_pending(up):
            return up
        try:
            return abs(up)
        except:
            return make_pending("abs", "cannot get absolute value")

    def _b_sqrt(self, up, args, kw, env):
        if is_pending(up):
            return up
        try:
            if up < 0:
                return make_pending("sqrt", "negative number")
            return math.sqrt(up)
        except:
            return make_pending("sqrt", "invalid input")

    def _b_floor(self, up, args, kw, env):
        if is_pending(up):
            return up
        try:
            return math.floor(up)
        except:
            return make_pending("floor", "invalid input")

    def _b_ceil(self, up, args, kw, env):
        if is_pending(up):
            return up
        try:
            return math.ceil(up)
        except:
            return make_pending("ceil", "invalid input")

    def _b_round(self, up, args, kw, env):
        if is_pending(up):
            return up
        digits = args[0] if args else 0
        try:
            return round(up, int(digits))
        except:
            return make_pending("round", "invalid input")

    def _b_min(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            if not up.seq:
                return make_pending("min", "empty table")
            try:
                return min(x for x in up.seq if not is_pending(x))
            except:
                return make_pending("min", "cannot compare elements")
        if args:
            b = args[0]
            if is_pending(b):
                return b
            try:
                return min(up, b)
            except:
                return make_pending("min", "incompatible types")
        return make_pending("min", "missing argument")

    def _b_max(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            if not up.seq:
                return make_pending("max", "empty table")
            try:
                return max(x for x in up.seq if not is_pending(x))
            except:
                return make_pending("max", "cannot compare elements")
        if args:
            b = args[0]
            if is_pending(b):
                return b
            try:
                return max(up, b)
            except:
                return make_pending("max", "incompatible types")
        return make_pending("max", "missing argument")

    def _b_eq(self, up, args, kw, env):
        if is_pending(up) or (args and is_pending(args[0])):
            return PENDING
        if not args:
            return make_pending("eq", "missing argument")
        return up == args[0]

    def _b_ne(self, up, args, kw, env):
        if is_pending(up) or (args and is_pending(args[0])):
            return PENDING
        if not args:
            return make_pending("ne", "missing argument")
        return up != args[0]

    def _b_lt(self, up, args, kw, env):
        if is_pending(up) or (args and is_pending(args[0])):
            return PENDING
        if not args:
            return make_pending("lt", "missing argument")
        try:
            return up < args[0]
        except:
            return make_pending("lt", "incomparable types")

    def _b_le(self, up, args, kw, env):
        if is_pending(up) or (args and is_pending(args[0])):
            return PENDING
        if not args:
            return make_pending("le", "missing argument")
        try:
            return up <= args[0]
        except:
            return make_pending("le", "incomparable types")

    def _b_gt(self, up, args, kw, env):
        if is_pending(up) or (args and is_pending(args[0])):
            return PENDING
        if not args:
            return make_pending("gt", "missing argument")
        try:
            return up > args[0]
        except:
            return make_pending("gt", "incomparable types")

    def _b_ge(self, up, args, kw, env):
        if is_pending(up) or (args and is_pending(args[0])):
            return PENDING
        if not args:
            return make_pending("ge", "missing argument")
        try:
            return up >= args[0]
        except:
            return make_pending("ge", "incomparable types")

    def _b_and(self, up, args, kw, env):
        if not args:
            return make_pending("and", "missing argument")
        b = args[0]
        up_false = up is False or up == 0
        b_false = b is False or b == 0
        if up_false or b_false:
            return False
        if is_pending(up) or is_pending(b):
            return PENDING
        return bool(up and b)

    def _b_or(self, up, args, kw, env):
        if not args:
            return make_pending("or", "missing argument")
        b = args[0]
        if up is True or b is True:
            return True
        if is_pending(up) or is_pending(b):
            return PENDING
        return bool(up or b)

    def _b_not(self, up, args, kw, env):
        if is_pending(up):
            return PENDING
        return not up

    def _b_is(self, up, args, kw, env):
        if not args:
            return make_pending("is", "missing argument")
        check = args[0]
        if is_pending(check):
            return is_pending(up)
        if check == "Int":
            return isinstance(up, int) and not isinstance(up, bool)
        if check == "Float":
            return isinstance(up, float)
        if check == "Bool":
            return isinstance(up, bool)
        if check == "String":
            return isinstance(up, str)
        if check == "Table":
            return isinstance(up, LipTable)
        if check == "Block":
            return isinstance(up, LipBlock)
        if check == "Pending":
            return is_pending(up)
        return False

    def _b_type(self, up, args, kw, env):
        if is_pending(up):
            return "Pending"
        if isinstance(up, bool):
            return "Bool"
        if isinstance(up, int):
            return "Int"
        if isinstance(up, float):
            return "Float"
        if isinstance(up, str):
            return "String"
        if isinstance(up, LipTable):
            return "Table"
        if isinstance(up, LipBlock):
            return "Block"
        return "Unknown"

    def _b_as(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("as", "missing type argument")
        target = args[0]
        try:
            if target == "Int":
                return int(up)
            if target == "Float":
                return float(up)
            if target == "Bool":
                return bool(up)
            if target == "String":
                return self._display(up)
        except:
            return make_pending("as", f"cannot convert to {target}")
        return make_pending("as", f"unknown type: {target}")

    def _b_upper(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, str):
            return up.upper()
        return make_pending("upper", "not a string")

    def _b_lower(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, str):
            return up.lower()
        return make_pending("lower", "not a string")

    def _b_trim(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, str):
            return up.strip()
        return make_pending("trim", "not a string")

    def _b_split(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, str):
            return make_pending("split", "not a string")
        sep = args[0] if args else " "
        parts = up.split(sep)
        return LipTable(parts)

    def _b_join(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("join", "not a table")
        sep = args[0] if args else ""
        try:
            return sep.join(self._display(x) for x in up.seq)
        except:
            return make_pending("join", "join failed")

    def _b_concat(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, str):
            result = up
            for arg in args:
                if is_pending(arg):
                    return arg
                result += self._display(arg)
            return result
        if isinstance(up, LipTable):
            result = LipTable(up.seq.copy(), up.named.copy())
            for arg in args:
                if is_pending(arg):
                    return arg
                if isinstance(arg, LipTable):
                    result = result.merge(arg)
                else:
                    result = result.append(arg)
            return result
        return make_pending("concat", "cannot concat this type")

    def _b_replace(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, str):
            return make_pending("replace", "not a string")
        if len(args) < 2:
            return make_pending("replace", "need old and new strings")
        old, new = args[0], args[1]
        if is_pending(old) or is_pending(new):
            return make_pending("replace", "pending argument")
        return up.replace(str(old), str(new))

    def _b_slice(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("slice", "missing start index")
        start = args[0]
        end = args[1] if len(args) > 1 else None
        if is_pending(start):
            return start
        if isinstance(up, str):
            if end is None:
                return up[int(start) :]
            return up[int(start) : int(end)]
        if isinstance(up, LipTable):
            if end is None:
                return LipTable(up.seq[int(start) :], {})
            return LipTable(up.seq[int(start) : int(end)], {})
        return make_pending("slice", "cannot slice this type")

    def _b_contains(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("contains", "missing argument")
        needle = args[0]
        if is_pending(needle):
            return needle
        if isinstance(up, str):
            return str(needle) in up
        if isinstance(up, LipTable):
            for item in up.seq:
                if item == needle:
                    return True
            return False
        return make_pending("contains", "cannot check contains on this type")

    def _b_starts_with(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("starts_with", "missing argument")
        if isinstance(up, str):
            return up.startswith(str(args[0]))
        return make_pending("starts_with", "not a string")

    def _b_ends_with(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("ends_with", "missing argument")
        if isinstance(up, str):
            return up.endswith(str(args[0]))
        return make_pending("ends_with", "not a string")

    def _b_print(self, up, args, kw, env):
        print(self._display(up))
        return up

    def _b_log(self, up, args, kw, env):
        print(f"[LOG] {self._display(up)}")
        return up

    def _b_warn(self, up, args, kw, env):
        print(f"[WARN] {self._display(up)}", file=sys.stderr)
        return up

    def _display(self, val: Any) -> str:
        if is_pending(val):
            return f"?({val.reason})"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, str):
            return val
        if isinstance(val, LipTable):
            return repr(val)
        if isinstance(val, LipBlock):
            return repr(val)
        return str(val)

    def _b_recover(self, up, args, kw, env):
        if is_pending(up):
            if args and isinstance(args[0], LipBlock):
                return self._call_block(args[0], [], {}, env)
            elif args:
                return args[0]
            return PENDING
        return up

    def _b_on_pending(self, up, args, kw, env):
        if is_pending(up):
            if args and isinstance(args[0], LipBlock):
                trace_table = LipTable(
                    [],
                    {
                        "file": up.file,
                        "line": up.line,
                        "operation": up.operation,
                        "reason": up.reason,
                        "chain": LipTable(up.chain),
                    },
                )
                self._call_block(args[0], [trace_table], {}, env)
        return up

    def _b_run(self, up, args, kw, env):
        if isinstance(up, Dispatch):
            selected = up.selected
            if isinstance(selected, LipBlock):
                if selected.params:
                    return self._call_block(selected, [up.original_value], {}, env)
                else:
                    return self._call_block(selected, [], {}, env)
            return selected
        if isinstance(up, LipBlock):
            return self._call_block(up, list(args), kw, env)
        return make_pending("run", "expected block or dispatch")

    def _b_map(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("map", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("map", "missing block argument")
        block = args[0]
        results = []
        for item in up.seq:
            results.append(self._call_block(block, [item], {}, env))
        return LipTable(results, up.named.copy())

    def _b_filter(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("filter", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("filter", "missing block argument")
        block = args[0]
        results = []
        for item in up.seq:
            cond = self._call_block(block, [item], {}, env)
            if cond is True:
                results.append(item)
        return LipTable(results)

    def _b_reduce(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("reduce", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("reduce", "missing block argument")
        block = args[0]
        acc = kw.get("init", PENDING)
        start_idx = 0
        if is_pending(acc) and up.seq:
            acc = up.seq[0]
            start_idx = 1
        for i in range(start_idx, len(up.seq)):
            acc = self._call_block(block, [acc, up.seq[i]], {}, env)
        return acc

    def _b_each(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("each", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("each", "missing block argument")
        block = args[0]
        for item in up.seq:
            self._call_block(block, [item], {}, env)
        return up

    def _b_find(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("find", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("find", "missing block argument")
        block = args[0]
        for item in up.seq:
            result = self._call_block(block, [item], {}, env)
            if result is True:
                return item
        return make_pending("find", "not found")

    def _b_every(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("every", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("every", "missing block argument")
        block = args[0]
        for item in up.seq:
            result = self._call_block(block, [item], {}, env)
            if result is not True:
                return False
        return True

    def _b_some(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("some", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("some", "missing block argument")
        block = args[0]
        for item in up.seq:
            result = self._call_block(block, [item], {}, env)
            if result is True:
                return True
        return False

    def _b_flatmap(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("flatmap", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("flatmap", "missing block argument")
        block = args[0]
        results = []
        for item in up.seq:
            result = self._call_block(block, [item], {}, env)
            if isinstance(result, LipTable):
                results.extend(result.seq)
            else:
                results.append(result)
        return LipTable(results)

    def _b_pairs(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("pairs", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("pairs", "missing block argument")
        block = args[0]
        for k, v in up.named.items():
            self._call_block(block, [k, v], {}, env)
        return up

    def _b_range(self, up, args, kw, env):
        if is_pending(up):
            return up
        try:
            start = int(up)
            end = int(args[0]) if args else start
            if not args:
                start, end = 0, start
            step = int(kw.get("step", 1)) if "step" in kw else 1
            return LipTable(list(range(start, end, step)))
        except:
            return make_pending("range", "invalid range arguments")

    def _b_length(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            return up.length()
        if isinstance(up, str):
            return len(up)
        return make_pending("length", "not a table or string")

    def _b_keys(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            return LipTable(up.keys())
        return make_pending("keys", "not a table")

    def _b_values(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            return LipTable(up.values())
        return make_pending("values", "not a table")

    def _b_has(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("has", "missing key argument")
        if isinstance(up, LipTable):
            key = args[0]
            if isinstance(key, str):
                return key in up.named
            if isinstance(key, int):
                return 0 <= key < len(up.seq)
        return False

    def _b_get(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not args:
            return make_pending("get", "missing key")
        if isinstance(up, LipTable):
            return up.get(args[0])
        if isinstance(up, str):
            idx = args[0]
            if isinstance(idx, int):
                if 0 <= idx < len(up):
                    return up[idx]
                return make_pending("get", "string index out of range")
        return make_pending("get", "cannot get from this type")

    def _b_set(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("set", "not a table")
        if len(args) < 2:
            return make_pending("set", "missing key or value")
        return up.set(args[0], args[1])

    def _b_append(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("append", "not a table")
        if not args:
            return make_pending("append", "missing value")
        return up.append(args[0])

    def _b_first(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            if up.seq:
                return up.seq[0]
            return make_pending("first", "empty table")
        if isinstance(up, str):
            if up:
                return up[0]
            return make_pending("first", "empty string")
        return make_pending("first", "not a table or string")

    def _b_last(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            if up.seq:
                return up.seq[-1]
            return make_pending("last", "empty table")
        if isinstance(up, str):
            if up:
                return up[-1]
            return make_pending("last", "empty string")
        return make_pending("last", "not a table or string")

    def _b_take(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("take", "not a table")
        n = int(args[0]) if args else 1
        return LipTable(up.seq[:n], {})

    def _b_drop(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("drop", "not a table")
        n = int(args[0]) if args else 1
        return LipTable(up.seq[n:], {})

    def _b_reverse(self, up, args, kw, env):
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            return LipTable(up.seq[::-1], up.named.copy())
        if isinstance(up, str):
            return up[::-1]
        return make_pending("reverse", "cannot reverse this type")

    def _b_sort(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("sort", "not a table")
        desc = kw.get("desc", False)
        try:
            sorted_seq = sorted(up.seq, reverse=bool(desc))
            return LipTable(sorted_seq)
        except:
            return make_pending("sort", "cannot compare elements")

    def _b_sort_by(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("sort_by", "not a table")
        if not args or not isinstance(args[0], LipBlock):
            return make_pending("sort_by", "missing block argument")
        block = args[0]
        desc = kw.get("desc", False)
        try:
            sorted_seq = sorted(
                up.seq,
                key=lambda x: self._call_block(block, [x], {}, env),
                reverse=bool(desc),
            )
            return LipTable(sorted_seq)
        except:
            return make_pending("sort_by", "sort failed")

    def _b_merge(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("merge", "not a table")
        if not args:
            return up
        result = up
        for arg in args:
            if is_pending(arg):
                return arg
            if isinstance(arg, LipTable):
                result = result.merge(arg)
            else:
                return make_pending("merge", "argument is not a table")
        return result

    def _b_flatten(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("flatten", "not a table")
        result = []
        for item in up.seq:
            if isinstance(item, LipTable):
                result.extend(item.seq)
            else:
                result.append(item)
        return LipTable(result)

    def _b_zip(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("zip", "not a table")
        if not args:
            return make_pending("zip", "missing second table")
        other = args[0]
        if is_pending(other):
            return other
        if not isinstance(other, LipTable):
            return make_pending("zip", "argument is not a table")
        result = []
        for i in range(min(len(up.seq), len(other.seq))):
            result.append(LipTable([up.seq[i], other.seq[i]]))
        return LipTable(result)

    def _b_sum(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("sum", "not a table")
        try:
            total = 0
            for item in up.seq:
                if is_pending(item):
                    return item
                total += item
            return total
        except:
            return make_pending("sum", "cannot sum elements")

    def _b_avg(self, up, args, kw, env):
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("avg", "not a table")
        if not up.seq:
            return make_pending("avg", "empty table")
        try:
            total = 0
            for item in up.seq:
                if is_pending(item):
                    return item
                total += item
            return total / len(up.seq)
        except:
            return make_pending("avg", "cannot average elements")

    def _b_spread(self, up, args, kw, env):
        """Spread table elements as individual values (returns the table itself for iteration)"""
        if is_pending(up):
            return up
        if isinstance(up, LipTable):
            return up
        return make_pending("spread", "not a table")

    def _b_remove(self, up, args, kw, env):
        """Remove element by index or key"""
        if is_pending(up):
            return up
        if not isinstance(up, LipTable):
            return make_pending("remove", "not a table")
        if not args:
            return make_pending("remove", "missing index or key")
        key = args[0]
        if is_pending(key):
            return key
        if isinstance(key, int):
            if 0 <= key < len(up.seq):
                new_seq = up.seq[:key] + up.seq[key + 1 :]
                return LipTable(new_seq, up.named.copy())
            return make_pending("remove", "index out of range")
        if isinstance(key, str):
            if key in up.named:
                new_named = {k: v for k, v in up.named.items() if k != key}
                return LipTable(up.seq.copy(), new_named)
            return make_pending("remove", f"key '{key}' not found")
        return make_pending("remove", "invalid key type")

    # ========== Method Wrappers ==========

    def _m_length(self, obj, args, kw, env):
        return self._b_length(obj, args, kw, env)

    def _m_keys(self, obj, args, kw, env):
        return self._b_keys(obj, args, kw, env)

    def _m_values(self, obj, args, kw, env):
        return self._b_values(obj, args, kw, env)

    def _m_has(self, obj, args, kw, env):
        return self._b_has(obj, args, kw, env)

    def _m_get(self, obj, args, kw, env):
        return self._b_get(obj, args, kw, env)

    def _m_set(self, obj, args, kw, env):
        return self._b_set(obj, args, kw, env)

    def _m_append(self, obj, args, kw, env):
        return self._b_append(obj, args, kw, env)

    def _m_merge(self, obj, args, kw, env):
        return self._b_merge(obj, args, kw, env)

    def _m_map(self, obj, args, kw, env):
        return self._b_map(obj, args, kw, env)

    def _m_filter(self, obj, args, kw, env):
        return self._b_filter(obj, args, kw, env)

    def _m_reduce(self, obj, args, kw, env):
        return self._b_reduce(obj, args, kw, env)

    def _m_each(self, obj, args, kw, env):
        return self._b_each(obj, args, kw, env)

    def _m_pairs(self, obj, args, kw, env):
        return self._b_pairs(obj, args, kw, env)

    def _m_take(self, obj, args, kw, env):
        return self._b_take(obj, args, kw, env)

    def _m_drop(self, obj, args, kw, env):
        return self._b_drop(obj, args, kw, env)

    def _m_first(self, obj, args, kw, env):
        return self._b_first(obj, args, kw, env)

    def _m_last(self, obj, args, kw, env):
        return self._b_last(obj, args, kw, env)

    def _m_reverse(self, obj, args, kw, env):
        return self._b_reverse(obj, args, kw, env)

    def _m_sort(self, obj, args, kw, env):
        return self._b_sort(obj, args, kw, env)

    def _m_sort_by(self, obj, args, kw, env):
        return self._b_sort_by(obj, args, kw, env)

    def _m_sum(self, obj, args, kw, env):
        return self._b_sum(obj, args, kw, env)

    def _m_avg(self, obj, args, kw, env):
        return self._b_avg(obj, args, kw, env)

    def _m_min(self, obj, args, kw, env):
        return self._b_min(obj, args, kw, env)

    def _m_max(self, obj, args, kw, env):
        return self._b_max(obj, args, kw, env)

    def _m_flatten(self, obj, args, kw, env):
        return self._b_flatten(obj, args, kw, env)

    def _m_zip(self, obj, args, kw, env):
        return self._b_zip(obj, args, kw, env)

    def _m_find(self, obj, args, kw, env):
        return self._b_find(obj, args, kw, env)

    def _m_every(self, obj, args, kw, env):
        return self._b_every(obj, args, kw, env)

    def _m_some(self, obj, args, kw, env):
        return self._b_some(obj, args, kw, env)

    def _m_contains(self, obj, args, kw, env):
        return self._b_contains(obj, args, kw, env)

    def _m_upper(self, obj, args, kw, env):
        return self._b_upper(obj, args, kw, env)

    def _m_lower(self, obj, args, kw, env):
        return self._b_lower(obj, args, kw, env)

    def _m_trim(self, obj, args, kw, env):
        return self._b_trim(obj, args, kw, env)

    def _m_split(self, obj, args, kw, env):
        return self._b_split(obj, args, kw, env)

    def _m_join(self, obj, args, kw, env):
        return self._b_join(obj, args, kw, env)

    def _m_concat(self, obj, args, kw, env):
        return self._b_concat(obj, args, kw, env)

    def _m_replace(self, obj, args, kw, env):
        return self._b_replace(obj, args, kw, env)

    def _m_starts_with(self, obj, args, kw, env):
        return self._b_starts_with(obj, args, kw, env)

    def _m_ends_with(self, obj, args, kw, env):
        return self._b_ends_with(obj, args, kw, env)

    def _m_slice(self, obj, args, kw, env):
        return self._b_slice(obj, args, kw, env)


# ============================================================
# Public API
# ============================================================


def create_interpreter() -> Interpreter:
    return Interpreter()


def run_source(source: str, interp: Interpreter = None) -> Any:
    from lip_lang import parse

    if interp is None:
        interp = create_interpreter()
    ast = parse(source)
    return interp.eval(ast)


def lip_repr(val: Any) -> str:
    if is_pending(val):
        return f"?({val.reason})"
    if val is None:
        return "nil"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        return f'"{val}"'
    if isinstance(val, LipTable):
        return repr(val)
    if isinstance(val, LipBlock):
        return repr(val)
    if isinstance(val, Dispatch):
        return f"<dispatch: {lip_repr(val.selected)}>"
    return str(val)
