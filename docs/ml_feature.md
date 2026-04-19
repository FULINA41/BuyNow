# Context & Architecture Decision

You are a Staff-Level Quant Engineer assisting me in building "BuyNow AI".
Tech Stack: Python, FastAPI, Polars, PyTorch, Next.js, Google Cloud Run.

**CRITICAL ARCHITECTURE DECISION:** We are building a "Global Panel Model" (One model for the entire stock universe), NOT per-ticker models. To capture idiosyncratic stock behaviors, our PyTorch model (`TonyNet`) MUST include an `nn.Embedding` layer for the ticker IDs, concatenated with the technical features.

# Master Development Plan

Please read the 4 steps below. **DO NOT generate all code at once.** Only generate the code for the Step 3 specify, and wait for my instruction to proceed.

## Step 1: Feature Engineering & Dataset Generation (Polars + Panel Data)

- `backend/app/ml/features.py`: Write `calculate_features_polars(df: pl.DataFrame) -> pl.DataFrame`. It must take a stacked panel dataframe (multiple tickers) and calculate features (e.g., RSI, MACD, Volatility) grouped by `ticker` using purely vectorized Polars operations. **[NEW]** Write a `build_ticker_mapping(tickers: list) -> dict` function that includes an `<UNK>: 0` placeholder for out-of-vocabulary handling, and save this dictionary as `ticker_vocab.json`.
- `backend/train/data_loader.py`: Script to download daily data for a universe of tickers (e.g., NVDA, MSFT, TSLA) via `alpaca-py`, stack them into a long format, calculate target labels based on 1-5 day forward returns, and save as a single local `panel_data.parquet`.

## Step 2: Global Model Training (PyTorch MPS) & Artifact Export

- `backend/app/ml/model.py`: Define `AlphaNet(nn.Module)`. It must take two inputs: `(features_tensor, ticker_id_tensor)`. **[NEW]** The `nn.Embedding` layer's `num_embeddings` must dynamically read the length from `ticker_vocab.json`. Pass the `ticker_id` through the embedding layer, concatenate with `features_tensor`, and pass through an MLP. Include a `ModelManager` singleton.
- `backend/train/trainer.py`: Write a training loop for Mac MPS (`device="mps"`). **[NEW]** Enforce a strict Time-Series Split (e.g., first 80% chronological for training, last 20% for validation) to prevent lookahead bias. It reads the parquet, applies features, and trains the global model predicting forward returns. Save weights to `global_alpha.pth`.

## Step 3: Fast Inference API (Cloud Run Backend)

- `backend/app/api/endpoints/predict.py`: FastAPI endpoint `GET /api/v1/predict/{ticker}`.
- Logic: **[NEW]** On startup, globally load both the model(based one the model name of the input ALphaNet or LightBGM) by using model manager and `ticker_vocab.json`. When called, fetch the last `MAX_LOOKBACK_DAYS` (e.g., 90 days, ensuring enough data for rolling features) for `{ticker}`, apply Polars features, convert the ticker to its ID (safely falling back to the `<UNK>` ID if not found in vocab, and this rule only for AlphaNet not suit for LightBGM), and run predict method in model manager inference. Return the signal(there are multiple return for AlphaNet).

## Step 4: Next.js Frontend Quant Dashboard

- `frontend/components/AlphaSignalPanel.tsx`: A sleek Tailwind dashboard component to display the inference result (Signal, Confidence Bar, Key Factors).
- `frontend/app/stock/[ticker]/page.tsx`: Show how to mount the component.

# Instruction

Acknowledge this updated architecture (Global Model + Ticker Embedding with Out-of-Vocabulary handling and strict Time-Series splitting). Then, generate ONLY the code for **Step 1 (`features.py` and `data_loader.py`)**. Wait for my approval.
