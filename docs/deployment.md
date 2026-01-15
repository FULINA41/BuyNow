# 部署指南

## GCP Cloud Run 部署（后端）

### 前置要求

1. 安装 [gcloud CLI](https://cloud.google.com/sdk/docs/install)
2. 创建 GCP 项目
3. 启用必要的 API：
   ```bash
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable containerregistry.googleapis.com
   ```

### 部署步骤

#### 方法 1: 使用 Cloud Build（推荐）

```bash
cd backend

# 设置项目 ID
export PROJECT_ID=your-gcp-project-id

# 提交构建
gcloud builds submit --config cloudbuild.yaml --project $PROJECT_ID
```

#### 方法 2: 手动部署

```bash
cd backend

# 1. 构建镜像
gcloud builds submit --tag gcr.io/$PROJECT_ID/engineer-alpha-api

# 2. 部署到 Cloud Run
gcloud run deploy engineer-alpha-api \
  --image gcr.io/$PROJECT_ID/engineer-alpha-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 60s \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars="ALLOWED_ORIGINS=https://yourdomain.com"
```

### 获取服务 URL

部署完成后，会显示服务 URL，例如：
```
https://engineer-alpha-api-xxx-uc.a.run.app
```

将此 URL 设置为前端的 `NEXT_PUBLIC_API_URL`。

## Vercel 部署（前端）

### 前置要求

1. 安装 [Vercel CLI](https://vercel.com/docs/cli)
2. 登录 Vercel: `vercel login`

### 部署步骤

```bash
cd frontend

# 首次部署
vercel

# 生产环境部署
vercel --prod
```

### 环境变量配置

在 Vercel 控制台设置以下环境变量：

- `NEXT_PUBLIC_API_URL`: 后端 API URL
- `NEXTAUTH_SECRET`: 随机字符串（用于加密）
- `NEXTAUTH_URL`: 前端域名
- `GOOGLE_CLIENT_ID`: Google OAuth Client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth Client Secret

### 通过 GitHub 自动部署

1. 将代码推送到 GitHub
2. 在 Vercel 控制台导入项目
3. 配置环境变量
4. 每次 push 到 main 分支会自动部署

## Google OAuth 配置

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建 OAuth 2.0 客户端 ID
3. 添加授权重定向 URI: `https://yourdomain.com/api/auth/callback/google`
4. 复制 Client ID 和 Client Secret

## 成本估算

### GCP Cloud Run（低流量场景）

- 每月 200 万次免费请求
- 360,000 GB-秒免费计算时间
- 180,000 vCPU-秒免费计算时间

**估算**：100 次请求/天 × 30 天 = 3,000 次/月（远低于免费额度）

### Vercel

- Hobby 计划：免费（个人项目）

**总成本**：~$0/月（在免费额度内）
