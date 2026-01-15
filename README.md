engineer-alpha-risk-tool/
├── backend/              # FastAPI Backend
│   ├── app/
│   │   ├── main.py       # FastAPI Entry Point
│   │   ├── routers/      # API Routes
│   │   ├── services/     # Business Logic
│   │   ├── models/       # Data Models
│   │   └── utils/        # Utility Functions
│   ├── Dockerfile
│   ├── requirements.txt
│   └── cloudbuild.yaml
│
├── frontend/             # Next.js Frontend
│   ├── app/              # App Router
│   ├── components/       # React Components
│   ├── lib/              # Utility Libraries
│   └── package.json
│
└── app.py                # Original Streamlit App (Legacy)