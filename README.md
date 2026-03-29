# liplay

**`Lip`核心特性解释器**

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
- 其他语言接口
