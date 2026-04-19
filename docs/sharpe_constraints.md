# Sharpe Ratio 约束说明（`optimize_max_sharpe`）

> 本文档解释 `backend/app/utils/quant_engine.py::PortfolioOptimizer.optimize_max_sharpe`
> 在"最大化 Sharpe"过程中施加的所有约束、惩罚项以及数值稳健性处理。
> 所有公式与默认值均与代码一一对应。

---

## 0. 目标函数

设组合权重向量为 \(w \in \mathbb{R}^n\)，年化期望收益向量为 \(\mu\)，年化协方差矩阵为 \(\Sigma\)，无风险利率为 \(r_f\)。

原始 Sharpe 比率：

\[
\text{Sharpe}(w) = \frac{w^\top \mu - r_f}{\sqrt{w^\top \Sigma w}}
\]

代码中**实际最小化**的目标不是 \(-\text{Sharpe}\)，而是带两项惩罚的形式：

\[
f(w) \;=\; -\,\text{Sharpe}(w) \;+\; \lambda_{L2}\sum_i w_i^2 \;+\; \lambda_{vol}\sum_i w_i \sigma_i
\]

其中 \(\sigma_i = \sqrt{\Sigma_{ii}}\) 为单资产年化波动率。

| 符号 | 默认值 | 来源（`optimize_max_sharpe` 形参 / 局部变量） |
|---|---|---|
| \(r_f\) | `0.04` | `risk_free_rate` |
| \(\lambda_{L2}\) | `0.1` | `l2_lambda` |
| \(\lambda_{vol}\) | `0.5` | `vol_penalty` |

> 因此输出字段 `sharpe_ratio` 是**用最优权重 \(w^\*\) 重新计算的"未加惩罚的"原始 Sharpe**（见函数末尾 `sharpe = (port_ret - risk_free_rate) / port_vol`），而不是 \(-f(w^\*)\)。惩罚仅作用于"挑选 \(w\)"这一步。

---

## 1. 硬约束（Hard Constraints）

通过 SciPy `minimize(method="SLSQP", bounds=..., constraints=...)` 强制满足。

### 1.1 权重边界（bounds）

```python
bounds = tuple((0.05, 1.0) for _ in range(n))
```

- 每个资产的权重 \(w_i \in [0.05,\; 1.0]\)。
- **下界 0.05**：避免出现"几乎为 0"的零碎仓位，相当于强制每个候选标的至少 5%（隐含的最少持仓 = 1/0.05 = 20 个，超过会因 \(\Sigma w_i = 1\) 不可行而失败）。
- **上界 1.0**：允许单资产极端情况，但实际会被下面的波动率上限和惩罚项压回来。

### 1.2 等式约束：满仓

```python
{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
```

\[
\sum_i w_i = 1
\]

仅做权重归一化，不允许杠杆 / 不允许做空（结合下界 \(\geq 0.05 > 0\)，自然 long-only）。

### 1.3 不等式约束：年化波动率上限

```python
if max_annual_vol is not None:
    _max_var = max_annual_vol ** 2
    constraints.append(
        {"type": "ineq", "fun": lambda w: _max_var - w @ cov_matrix.values @ w}
    )
```

\[
w^\top \Sigma w \;\leq\; \sigma_{\max}^2,\qquad \sigma_{\max} = 0.23 \text{ (默认)}
\]

- SLSQP 的不等式约定为 `fun(w) >= 0`，所以代码写成 `_max_var - wᵀΣw ≥ 0`。
- 默认 23% 年化波动率是上限。**这是直接限制"分母"以约束 Sharpe 不会通过抬高风险来虚高**。

---

## 2. 软约束（目标函数中的惩罚项）

这两项不会被求解器当成"约束"，而是改变最优解的形态，避免病态解。

### 2.1 L2 正则（防极端集中）

```python
l2_lambda = 0.1
penalty = l2_lambda * np.sum(weights ** 2)
```

\[
\lambda_{L2}\sum_i w_i^2,\qquad \lambda_{L2}=0.1
\]

- 在 \(\sum w_i = 1\) 的约束下，\(\sum w_i^2\) 在均匀分布时最小（= 1/n），在 one-hot 时最大（= 1）。
- 加上这一项相当于把 \(w\) 推向更均匀的分布，**抑制"全押单只票"**这种数学上 Sharpe 高、实际不可执行的解。

### 2.2 单资产波动率惩罚（偏好低波蓝筹）

```python
asset_vols = np.sqrt(np.diag(cov_matrix.values))
vol_drag = vol_penalty * (weights @ asset_vols)
```

\[
\lambda_{vol}\sum_i w_i \sigma_i,\qquad \lambda_{vol}=0.5
\]

- 对每个资产按其自身年化波动率线性加权扣分。
- 与 1.3 的"组合波动率上限"不同：1.3 限制 \(\sqrt{w^\top \Sigma w}\)（**含相关性**），这里限制 \(\sum w_i \sigma_i\)（**不含相关性**，类似按风险预算线性扣分）。
- 含义：**即使两只高波资产负相关、组合波动率不高，也会因为单只波动率高而被惩罚**，从而结构性偏向低波蓝筹。

### 2.3 协方差估计：Ledoit-Wolf 收缩（间接约束 Sharpe）

`calculate_returns_and_cov`：

```python
lw = LedoitWolf().fit(log_returns.values)
cov_matrix = pd.DataFrame(
    lw.covariance_ * TRADING_DAYS_PER_YEAR,
    ...
)
```

- 不使用样本协方差 `log_returns.cov()`，改用 **Ledoit-Wolf 收缩估计器**。
- 样本协方差在资产数 \(n\) 接近样本期 \(T\) 时会**严重低估某些方向上的风险**，导致 mean-variance 优化器疯狂利用估计噪声、把 Sharpe "刷"到不合理的高度。
- 收缩估计把样本协方差向一个有结构的目标矩阵（对角阵 / scaled identity）收缩，**等价于在协方差层面注入一个先验**，是约束 Sharpe 的最重要、最容易被忽视的一道防线。

---

## 3. 数值稳健性

### 3.1 零波动兜底

```python
if port_vol == 0:
    return 1e6
```

避免在数值上 \(w^\top \Sigma w = 0\) 时除零，把这种点变成"非常差"以便求解器远离。

### 3.2 求解器配置

```python
result = minimize(
    neg_sharpe, init_weights,
    method="SLSQP",
    bounds=bounds, constraints=constraints,
    options={"maxiter": 1000, "ftol": 1e-12},
)
```

- **SLSQP**：支持等式 + 不等式 + 边界混合约束的 SQP 方法，适合本问题规模（数十个资产）。
- 初值 `init_weights = 1/n`（等权），落在 1.1 的可行域内（除非 \(n > 20\)）。
- 不收敛时 `logger.warning`，仍会用 `result.x` 返回（**这是已知的弱点：失败时不会抛错**）。

### 3.3 报告口径

最终输出的 `sharpe_ratio` 字段：

```python
sharpe = (port_ret - risk_free_rate) / port_vol if port_vol > 0 else 0.0
```

- 是**未加惩罚的原始 Sharpe**（用 \(w^\*\) 算 \(\mu, \Sigma\)）。
- 因此前端看到的 Sharpe 数值已经是经过"波动率上限 + L2 + 波动率惩罚 + LW 收缩"四道约束**反向压低**之后的稳健值，比无约束 mean-variance 的纸面 Sharpe 要低，但实盘可执行性更强。

---

## 4. 约束总览表

| 约束类型 | 形式 | 默认参数 | 防止的失效模式 |
|---|---|---|---|
| 硬·边界 | \(0.05 \le w_i \le 1\) | — | 零碎仓位 / 做空 |
| 硬·等式 | \(\sum w_i = 1\) | — | 杠杆 / 空仓 |
| 硬·不等式 | \(w^\top \Sigma w \le \sigma_{\max}^2\) | \(\sigma_{\max}=0.23\) | 通过堆风险刷 Sharpe |
| 软·L2 | \(\lambda_{L2}\sum w_i^2\) | \(\lambda_{L2}=0.1\) | 全押单票的角点解 |
| 软·单资产波动 | \(\lambda_{vol}\sum w_i\sigma_i\) | \(\lambda_{vol}=0.5\) | 偏好高波资产 |
| 估计器 | Ledoit-Wolf 收缩协方差 | sklearn 默认 | 协方差估计噪声放大 |
| 数值 | `port_vol==0` 返回 1e6 | — | 除零 |
| 求解器 | SLSQP, ftol=1e-12, maxiter=1000 | — | 局部最优 / 不收敛 |

---

## 5. 调参指引（可选）

| 想要的效果 | 调哪一项 | 方向 |
|---|---|---|
| 组合更分散 | `l2_lambda` | ↑ |
| 更偏向低波蓝筹 | `vol_penalty` | ↑ |
| 允许更激进的高波组合 | `max_annual_vol` | ↑ 或设为 `None` 关闭 |
| 允许集中持仓 | `bounds` 下界 | ↓（如 0.0） |
| 更稳定但略保守的协方差 | 已使用 `LedoitWolf`，无需改 | — |

> **不构成投资建议**。本文档仅说明工程实现中对 Sharpe 比率施加的数学约束。
