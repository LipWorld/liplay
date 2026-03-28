# liplay
这是一个不完整且不全遵循定义的`Lip`解释器 -- just for fun!

## 实现了的特性（核心特性）

1. **基础类型**: `Int`, `Float`, `Bool`, `String`, `?` (Pending)
2. **Table**: 统一的列表/字典结构
3. **Block**: 匿名函数/闭包 `{ x: expr }`
4. **管道**: `->` 和捕获 `:>`
5. **三路分支**: `cond -> [b0, b1, b2] -> run()`
6. **Pending 处理**: `recover`, `is(?)`, `on_pending`, `.__trace__`
7. **集合操作**: `map`, `filter`, `reduce`, `each`, `pairs`
8. **基础内置函数**: 算术、比较、逻辑、字符串操作、I/O

## 延后实现的特性

- Tensor（需要大量数值计算支持）
- Class/Mixin（对象系统）
- Module/Import（模块系统）
- 并发/Actor
- 完整的 TCO

## 示例代码

```lip
-- 基本运算和管道
10 -> add(5) -> mul(2) -> print()

-- Table 和 Block
nums: [1, 2, 3, 4, 5]
nums -> map({ x: x -> mul(x) }) -> print()

-- 三路分支 # 注意这里实现的次序
true -> [{ : "false" }, { : "true" }, { : "pending" }] -> run() -> print()

-- Pending 处理
10 -> div(0) -> recover({ : 0 }) -> print()

-- 中途捕获
100 -> mul(2) :> doubled -> add(50) -> print()
doubled -> print()

-- reduce 求和
[1, 2, 3, 4, 5] -> reduce({ acc, x: acc -> add(x) }, init: 0) -> print()
```

这个实现涵盖了 Lip 语言的核心特性，包括三元逻辑、管道、Table、Block 和 Pending 状态处理。
