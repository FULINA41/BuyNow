# 架构说明

## 系统架构

```
┌─────────────┐
│   用户浏览器  │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────┐
│   Vercel    │  Next.js 前端
│  (Next.js)  │
└──────┬──────┘
       │ API 调用
       ▼
┌─────────────┐
│ Cloud Run   │  FastAPI 后端
│  (FastAPI)  │
└──────┬──────┘
       │ 获取数据
       ▼
┌─────────────┐
│  yfinance   │  股票数据 API
└─────────────┘
```

## 数据流

1. **用户输入** → 前端表单（Ticker、风格、历史长度）
2. **API 请求** → POST `/api/v1/analyze`
3. **后端处理**：
   - 加载价格数据（yfinance）
   - 计算技术指标（RSI、ATR、MA 等）
   - 生成信号（ABC 系统）
   - 评估风险
   - 计算买入区间
   - 获取基本面数据
4. **返回结果** → JSON 响应
5. **前端展示** → React 组件渲染

## 核心模块

### 后端服务模块

- `services/indicators.py`: 技术指标计算
  - RSI、ATR、MA、波动率、回撤
- `services/signals.py`: 信号生成
  - ABC 决策系统
- `services/risk.py`: 风险评估
  - 基于波动率、回撤、趋势
- `services/zones.py`: 买入区间计算
  - 保守、标准、激进三个区间
- `services/fundamentals.py`: 基本面分析
  - FCF Yield、PS Multiple 估值

### 前端组件

- `StockAnalyzer.tsx`: 主分析器组件
- `SignalCard.tsx`: 信号展示卡片
- `RiskBadge.tsx`: 风险徽章
- `BuyZones.tsx`: 买入区间展示

## 缓存策略

### 后端缓存

- **yfinance 数据**: 15 分钟内存缓存（`@lru_cache`）
- **基本面数据**: 15 分钟内存缓存

### 前端缓存

- 使用 SWR 进行客户端缓存（可选）

## 认证系统

- **NextAuth.js**: 支持 Google OAuth 和 Credentials
- **未来扩展**: 可对接 Supabase Auth

## 部署架构

### 后端（Cloud Run）

- **容器化**: Docker
- **自动扩缩容**: 0-10 实例
- **超时**: 60 秒
- **内存**: 2GB
- **CPU**: 2 vCPU

### 前端（Vercel）

- **静态生成**: Next.js SSG/ISR
- **边缘网络**: 全球 CDN
- **自动部署**: GitHub 集成

## 安全考虑

1. **CORS**: 后端配置允许的源
2. **环境变量**: 敏感信息不提交到代码库
3. **API 限流**: 未来可添加（Cloud Run 有内置限流）
4. **认证**: NextAuth.js 处理会话管理

## 扩展性

### 水平扩展

- Cloud Run 自动处理多实例
- 无状态设计，易于扩展

### 垂直扩展

- 可调整 Cloud Run 内存和 CPU
- 可启用最小实例数（减少冷启动）

### 未来扩展

- 数据库集成（Supabase）
- 实时通知（WebSocket）
- 图表可视化（Chart.js/Recharts）
