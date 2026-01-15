# Engineer Alpha - 全栈股票分析工具

将 Streamlit 应用重构为现代化的 Next.js + FastAPI 全栈应用。

## 项目结构

```
engineer-alpha-risk-tool/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── main.py       # FastAPI 入口
│   │   ├── routers/      # API 路由
│   │   ├── services/     # 业务逻辑
│   │   ├── models/       # 数据模型
│   │   └── utils/        # 工具函数
│   ├── Dockerfile
│   ├── requirements.txt
│   └── cloudbuild.yaml
│
├── frontend/             # Next.js 前端
│   ├── app/              # App Router
│   ├── components/       # React 组件
│   ├── lib/              # 工具库
│   └── package.json
│
└── app.py                # 原始 Streamlit 应用（保留）
```

## 技术栈

- **前端**: Next.js 14 + TypeScript + Tailwind CSS
- **后端**: FastAPI + Python 3.11
- **部署**: Vercel (前端) + GCP Cloud Run (后端)
- **认证**: NextAuth.js

## 快速开始

### 后端开发

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 运行开发服务器
uvicorn app.main:app --reload --port 8080
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 运行开发服务器
npm run dev
```

### Docker 构建（后端）

```bash
cd backend
docker build -t engineer-alpha-api .
docker run -p 8080:8080 engineer-alpha-api
```

## 环境变量

### 后端

创建 `backend/.env`:

```env
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### 前端

创建 `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXTAUTH_SECRET=your-secret-here
NEXTAUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

## 部署

### 后端部署到 GCP Cloud Run

```bash
cd backend

# 方法 1: 使用 gcloud CLI
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/engineer-alpha-api
gcloud run deploy engineer-alpha-api \
  --image gcr.io/YOUR_PROJECT_ID/engineer-alpha-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated

# 方法 2: 使用 Cloud Build（推荐）
gcloud builds submit --config cloudbuild.yaml
```

### 前端部署到 Vercel

```bash
cd frontend
vercel --prod
```

或通过 GitHub 集成自动部署。

## API 文档

启动后端后，访问：

- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## 功能特性

- ✅ 股票信号分析（ABC 系统）
- ✅ 风险评估
- ✅ 买入区间计算
- ✅ 基本面分析
- ✅ 加仓位置建议
- ✅ 用户认证（NextAuth.js）

## 未来扩展

- [ ] 保存分析历史到 Supabase
- [ ] 自选股列表
- [ ] 价格提醒/通知
- [ ] 交互式图表

## 免责声明

本工具仅用于研究与教育，不构成投资建议。市场有风险，投资需谨慎。
