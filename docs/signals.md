# 前端展示信号说明（Signals Reference）

> 本文件说明 `POST /api/v1/analyze` 返回、并在前端展示的**每一个字段**的计算方法与含义。
> 所有公式均来自 `backend/app/services/` 中的实现；展示层参考 `docs/app.py`。
> 本工具仅用于研究与教育，**不构成投资建议**。

---

## 0. 总览（前端卡片 ↔ 后端字段）

| 前端卡片 | 后端字段来源 | Pydantic 模型 |
|---|---|---|
| 建议动作（观察 / 试探 / 建仓 / 加仓） | `services/signals.py::signal_abc` | `SignalResponse` |
| 风险等级（🟢🟡🔴） | `services/risk.py::risk_level` | `RiskResponse` |
| 当前价格 Last | 价格序列最后一根收盘 | 共享字段 |
| 买入区间（保守 / 标准 / 激进） | `services/zones.py::buy_zones` | `ZonesResponse` |
| 加仓位置（首加 / 回调加 / 价值洼地加） | `services/zones.py::add_levels` | `AddLevelsResponse` |
| 基本面（PE/PS/PB/FCF/Revenue/MktCap…） | `services/fundamentals.py::get_fundamentals` | `FundamentalsResponse` |
| 公允价值（FairLow/Mid/High + Method） | `services/fundamentals.py::rough_fair_value_range` | `FairValueResponse` |
| 高级数据（MA50/MA200/Vol/DD/ATR） | 同上各模块 + `services/indicators.py` | 分散在 Risk / Zones |

---

## 1. 建议动作 —— ABC 信号（`Signal`）

**定位**：决定"现在该观察还是该分批介入"的**三条件闸门**，不预测涨跌。

### 1.1 三个子条件

| 名称 | 变量 | 判定 | 含义 |
|---|---|---|---|
| **A 位置偏低** | `A_pos` | 近 3 年分位 `Pct3Y < 0.30` **或** 近 5 年分位 `Pct5Y < 0.30` | 当前价格处在过去 3y/5y 收盘分布的**下 30%** |
| **B 情绪偏冷** | `B_rsi` | `RSI(14) < 35` | 短期超卖/偏冷 |
| **C 有回暖迹象** | `C_turn` | `RSI(t) > RSI(t-1)` | RSI 最近一根向上拐头（下跌动能减弱） |

### 1.2 RSI(14)（Wilder 平滑）

实现：`indicators.py::rsi_wilder`

```
delta     = close.diff()
gain      = max(delta, 0)
loss      = max(-delta, 0)
avg_gain  = EWM(gain, alpha = 1/14)
avg_loss  = EWM(loss, alpha = 1/14)
rs        = avg_gain / avg_loss
RSI       = 100 - 100 / (1 + rs)
```

> 使用 Wilder 的 `ewm(alpha=1/period)` 而非简单移动平均，贴近传统 RSI 定义。

### 1.3 分位数 `Pct3Y / Pct5Y`

实现：`indicators.py::pct_rank_window`

```
取最近 window 根收盘（756 ≈ 3 年 / 1260 ≈ 5 年），
对该窗口做 rank(pct=True)，返回最后一根的分位（0~1）。
```

- `Pct3Y = 0.12` 代表"当前价格比过去 3 年 88% 的交易日都低"。
- 数据不足返回 `NaN`，前端显示 "—"。

### 1.4 聚合成 `Signal`

```
A and B and C  → "Adding to a Position"   (加仓)
A and B        → "Building a Position"    (建仓)
A  or  B       → "Probing"                (试探)
else           → "Observation"            (观察)
```

**意义**：一张"可不可以开始分批"的红绿灯，不是买卖指令。

---

## 2. 风险等级（`Risk` / `RiskScore`）

**定位**：基于**波动 + 回撤 + 趋势 + 均线结构**的可解释评分，分数越高风险越大。

实现：`services/risk.py::risk_level`

### 2.1 基础量

| 字段 | 计算 | 说明 |
|---|---|---|
| `MA50` | `close.rolling(50).mean().iloc[-1]` | 50 日简单均线 |
| `MA200` | `close.rolling(200).mean().iloc[-1]` | 200 日简单均线 |
| `TrendUp` | `MA50 > MA200` | 长期趋势是否向上（"金叉侧") |
| `Vol` | `std(daily_ret) * √252` | **年化**波动率，需至少 50 条日收益 |
| `DD1Y` | `(last - max(last 252 close)) / max` | 近 1 年相对最高点的回撤（负数） |

### 2.2 评分规则（累加）

```
Vol > 0.60  +3   |  Vol > 0.45  +2   |  Vol > 0.30  +1
DD  < -0.40 +3   |  DD  < -0.30 +2   |  DD  < -0.15 +1
TrendUp == False +1
(MA50 - MA200) / MA200 < -0.10  +2        ← 距离过远（is_crashing）
```

### 2.3 死亡交叉（Death Cross）

- 条件：今日 `MA50 < MA200` 且前一日 `MA50 >= MA200`（当日下穿）。
- 仅在 `score >= 5` 时升级等级显示。

### 2.4 等级映射

```
score >= 5 and is_death_cross → "🔴 High Risk(Death Cross)"
score >= 5                    → "🔴 High Risk"
score >= 3                    → "🟡 Medium Risk"
else                          → "🟢 Low Risk"
```

**意义**：告诉用户"这只票此刻是**易碎**还是**稳健**"——不是看涨看跌信号，而是**仓位大小/节奏**的参考。

---

## 3. 当前价格 `Last`

- 取清洗后 `df["Close"]` 的最后一根收盘。
- 所有信号、买入区间、加仓位置都以它为锚。
- 注意：Price（基本面卡里的 `Price`）与 `Last` 可能不一致——`Last` 来自历史 OHLC 数据源（通常日频 + 可能延迟），`Price` 优先使用 Alpaca 的**15 分钟延迟**最新 1 分钟 bar 收盘。

---

## 4. 买入区间（`Conservative / Neutral / Aggressive`）

**定位**：一条"**分批带**"，不是预测底部；让用户按风格选择一个区间分批挂单。

实现：`services/zones.py::buy_zones`

### 4.1 ATR(14)

实现：`indicators.py::atr`

```
tr  = max( high-low ,  |high - prev_close| ,  |low - prev_close| )
ATR = tr.rolling(14).mean().iloc[-1]
atr_pct = ATR / last
```
> ATR 衡量**近期真实波动幅度**，用它把价格波动拉齐。

### 4.2 带宽 `width`

```
width = max(
    1.8 * ATR,
    last * max(0.06, 1.2 * atr_pct)
)
```
- **兜底下限 6%**：即便很平静的票，分批带也不会塌成一个点；
- **上限由 ATR 决定**：波动越大，分批带越宽。

### 4.3 中心 `center`（"偏向回调买"）

```
dev200      = (last - MA200) / MA200                # 价格偏离 200 日均线
center_disc = 0.10 + clip(dev200, -0.2, 0.2) * 0.10
center_disc = clip(center_disc, 0.06, 0.18)         # 限制在 6%~18%
center      = last * (1 - center_disc)
```

逻辑：**价格越高于 MA200，分批中心越往下折价**（避免在拉高后追涨）；
      价格越低于 MA200，折价越小（别一味等更深回调）。

### 4.4 三个区间

| 区间 | 公式 | 直觉 |
|---|---|---|
| 🟦 保守 `Conservative` | `[center + 0.6·width, center + 1.2·width]` | 比当前稍高，**等小回调**，丢失成本但安全 |
| 🟩 标准 `Neutral`      | `[center - 0.4·width, center + 0.4·width]` | 围绕分批中心的**主力区** |
| 🟥 激进 `Aggressive`   | `[center - 1.2·width, center - 0.6·width]` | **抄底带**，深回调才触发 |

所有区间经 `clamp(lo, hi)` 保证 `lo ≤ hi` 且 `> 0.01`。

**意义**：与"一口价抄底"对立。给三个并排带，让用户按 `conservative/standard/aggressive` 风格挑一个做分批。

---

## 5. 加仓位置（`AddLevelsResponse`）

实现：`services/zones.py::add_levels`

| 字段 | 公式 | 含义 |
|---|---|---|
| `FirstAdd` | `Neutral[0]`（标准区下沿） | 价格跌到**主力区下沿**时的第一次加仓点 |
| `PullbackAdd` | `(Aggressive[0] + Aggressive[1]) / 2`（抄底带中点） | 出现像样回调时的加仓点 |
| `ValuePocketAdd` | 见下 | **估值维度**的加仓触发价（与技术面无关） |
| `ValuePocketRule` | 与 `ValuePocketAdd` 对应的规则文本 | 便于前端解释为什么这个值 |

### `ValuePocketAdd` 计算规则

```
if FairLow is not None and FairLow > 0:
    ValuePocketAdd  = FairLow * 0.90
    ValuePocketRule = "价格 ≤ 0.9 × FairLow（估值折扣）"
elif FairMid is not None and FairMid > 0:
    ValuePocketAdd  = FairMid * 0.70
    ValuePocketRule = "价格 ≤ 0.7 × FairMid（估值折扣）"
else:
    ValuePocketAdd  = None
```

**意义**：技术买点告诉你"哪里开始分批"，估值加仓告诉你"跌到**明显便宜**时额外加码"。两套逻辑互为冗余。

---

## 6. 基本面（`FundamentalsResponse`）

实现：`services/fundamentals.py::get_fundamentals`（15 分钟缓存）

| 字段 | 含义 | 数据源优先级 |
|---|---|---|
| `Price` | 最新价格 | **Alpaca**（15 分钟延迟 1Min bar 收盘） → FMP quote → yfinance |
| `Shares` | 在外流通股本 | FMP `income-statement.weightedAverageShsOut` → yfinance `sharesOutstanding` |
| `MarketCap` | 市值 | FMP `quote.marketCap` → yfinance → **兜底：`Price × Shares`** |
| `RevenueTTM` | 近 12 月营收 | FMP: `revenuePerShareTTM × Shares` → yfinance `totalRevenue` |
| `FCF` | 近 12 月自由现金流 | FMP: `freeCashFlowPerShareTTM × Shares` → yfinance: `OCF − CapEx` |
| `PE`  | TTM 市盈率 | FMP `priceToEarningsRatioTTM` → yfinance `trailingPE` |
| `PS`  | TTM 市销率 | FMP `priceToSalesRatioTTM` → yfinance `priceToSalesTrailing12Months` |
| `PB`  | 市净率 | FMP `priceToBookRatioTTM` → yfinance `priceToBook` |

**降级策略**：FMP 先试；返回后对 `None` 字段用 yfinance 补齐；Price 再用 Alpaca 覆盖（因 Alpaca 免费额度拿不到实时，必须 end = now - 16min）。

**意义**：给**估值锚点**和**规模感**，不做精确 DCF，所以在公允价值里是"粗算"。

---

## 7. 公允价值锚点（`FairValueResponse`）

实现：`services/fundamentals.py::rough_fair_value_range`

### 7.1 方法一：FCF Yield 锚点（优先，适合有稳定现金流公司）

触发条件：`FCF > 0` 且 `MarketCap`、`Shares` 可用。

```
合理 FCF Yield 区间（粗）：6% / 4.5% / 3%
FairLow  = (FCF / 0.06)  / Shares      # 对应 "贵"  一端的下限
FairMid  = (FCF / 0.045) / Shares
FairHigh = (FCF / 0.03)  / Shares
Method   = "FCF Yield（粗算）"
```

> 直觉：把 FCF Yield 反推成市值 / 股价。要求越高的 yield → 锚价越低。

### 7.2 方法二：PS 倍数锚点（兜底，更普适更粗）

触发条件：`RevenueTTM > 0` 且 `Shares` 可用，且方法一不适用。

```
FairLow  = (Revenue * 4.0) / Shares
FairMid  = (Revenue * 6.0) / Shares
FairHigh = (Revenue * 8.0) / Shares
Method   = "PS Multiple（粗算）"
```

### 7.3 兜底

若两种方法都不可用：`Method = "N/A"`、三个 Fair 值全为 `None`，前端显示 "—"。

**意义**：不装作精准估值，**只**用来给 `ValuePocketAdd`（价值洼地加仓）一个**可复现的规则**。

---

## 8. 高级数据（"给懂的人看"）

这些字段已在上文各模块中出现，前端折叠展示，便于核对计算：

| 字段 | 来源 | 公式/定义 |
|---|---|---|
| `MA50`  | Risk  | 50 日收盘均线 |
| `MA200` | Risk  | 200 日收盘均线 |
| `TrendUp` | Risk | `MA50 > MA200` |
| `Vol`（年化波动率） | Risk | `std(pct_change) * √252`（需 ≥ 50 条日收益） |
| `DD1Y`（近 1 年回撤） | Risk | `(last − max(last 252 close)) / max`（负数） |
| `ATR14` | Zones | 14 日真实波幅均值 |
| `PE / PS / PB` | Fundamentals | 见第 6 节 |
| `FairLow / FairMid / FairHigh / Method` | FairValue | 见第 7 节 |

---

## 9. 安全约束与数据前置校验

`api/endpoints/analysis.py::analyze_stock` 在进入计算之前有硬门槛：

```
if "Close" not in df  or  len(df["Close"]) < 260:
    → HTTP 400 "data not enough or failed to load"
```

**意义**：没有约 1 年的日频数据时，所有分位数 / MA200 / 年化波动都不稳定，直接拒绝。

---

## 10. 常见问题

- **Q: 为什么 `Pct5Y` 有时是空？**
  A: 价格历史短于 1260 交易日（约 5 年），`pct_rank_window` 返回 `NaN`；`signal_abc` 只用 `Pct3Y` 兜底。

- **Q: 买入区间是不是底部预测？**
  A: **不是**。区间由 ATR + MA200 偏离生成，是"分批带"。出现新低时系统会自然下移，不假设底在哪。

- **Q: 为什么 `Price` 和 `Last` 不同？**
  A: `Last` 来自历史 OHLC（日频、调整后）；`Price` 优先 Alpaca 的 1Min bar（end = now−16min），更接近最新市况。两个字段各有用途，前端不强行合并。

- **Q: 风险等级为什么对 `death cross` 特别标注？**
  A: 50 日线**当日**下穿 200 日线（prev ≥ 且 today <）是经典趋势信号；仅在 `score >= 5` 时合并显示，避免单一信号误伤。

---

## 11. 源代码索引

| 概念 | 文件 | 关键函数 |
|---|---|---|
| ABC 信号 | `backend/app/services/signals.py` | `signal_abc` |
| 风险评分 | `backend/app/services/risk.py` | `risk_level` |
| 买入区间 / 加仓位置 | `backend/app/services/zones.py` | `buy_zones`, `add_levels` |
| 基本面 / 公允价值 | `backend/app/services/fundamentals.py` | `get_fundamentals`, `rough_fair_value_range` |
| 技术指标底层 | `backend/app/services/indicators.py` | `rsi_wilder`, `pct_rank_window`, `ma`, `annualized_vol`, `drawdown_1y`, `atr` |
| API 聚合 | `backend/app/api/endpoints/analysis.py` | `POST /api/v1/analyze` |
| 响应契约 | `backend/app/models/schemas.py` | `AnalysisResponse` 及子模型 |
