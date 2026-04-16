"""
LightGBM baseline for 5-day stock return prediction.

Replaces the PyTorch LSTM pipeline with a gradient-boosted tree model
that ingests summary statistics extracted from the same 20-day sliding
windows.  Strict chronological split — no data leakage.

Run from the backend/ directory:
    python -m train.train_lgbm
"""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
from app.ml.features import FEATURE_COLS  # noqa: E402
from train.trainer import _add_vol_target, _build_sequences  # noqa: E402

TARGET_COL = "fwd_ret_5d"
VOL_COL = "fwd_vol_5d"
SEQ_LEN = 20
TRAIN_RATIO = 0.8
EARLY_STOPPING_ROUNDS = 50


# ── 3D → 2D flattening ──────────────────────────────────────────────

def _flatten_sequences(
    features_3d: np.ndarray,
    feature_names: list[str],
) -> tuple[np.ndarray, list[str]]:
    """Convert (N, seq_len, F) sliding windows into (N, 3*F) tabular rows.

    For each feature extracts:
      - last  : value on the most recent day of the window
      - mean  : mean over the window
      - std   : standard deviation over the window

    Returns the 2D array and corresponding column names.
    """
    last = features_3d[:, -1, :]                        # (N, F)
    mean = features_3d.mean(axis=1)                     # (N, F)
    std = features_3d.std(axis=1)                       # (N, F)

    flat = np.concatenate([last, mean, std], axis=1)    # (N, 3*F)

    col_names = (
        [f"{c}_last" for c in feature_names]
        + [f"{c}_mean" for c in feature_names]
        + [f"{c}_std" for c in feature_names]
    )
    return flat, col_names


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")

    # ── Load panel data ──────────────────────────────────────────
    parquet_path = SCRIPT_DIR / "panel_data.parquet"
    df = pl.read_parquet(str(parquet_path))
    print(f"Loaded {len(df):,} rows  ({df['ticker'].n_unique()} tickers)")

    df = _add_vol_target(df)
    df = df.drop_nulls(subset=[VOL_COL])

    # ── Build 3D sliding windows (reuse existing logic) ──────────
    print(f"Building {SEQ_LEN}-day sliding windows …")
    features_3d, _ticker_ids, ret_targets, _vol_targets, dates = (
        _build_sequences(df, SEQ_LEN)
    )
    print(f"  → {len(features_3d):,} sequences, shape {features_3d.shape}")

    # ── Flatten to 2D ────────────────────────────────────────────
    X, col_names = _flatten_sequences(features_3d, FEATURE_COLS)
    y = ret_targets.astype(np.float64)
    print(f"  → Flattened X: {X.shape}  ({len(col_names)} features)")

    # ── Strict chronological split ───────────────────────────────
    unique_dates = np.unique(dates)
    unique_dates.sort()
    split_date = unique_dates[int(len(unique_dates) * TRAIN_RATIO)]

    train_mask = dates < split_date
    val_mask = ~train_mask

    X_train, X_val = X[train_mask], X[val_mask]
    y_train, y_val = y[train_mask], y[val_mask]
    print(
        f"  Train: {X_train.shape[0]:,}   "
        f"Val: {X_val.shape[0]:,}   "
        f"Split date: {split_date}"
    )

    # ── LightGBM datasets ────────────────────────────────────────
    ds_train = lgb.Dataset(X_train, label=y_train, feature_name=col_names)
    ds_val = lgb.Dataset(X_val, label=y_val, reference=ds_train)

    # ── Anti-overfitting hyperparameters ─────────────────────────
    params: dict = {
        "objective": "regression",
        "metric": "mse",
        "boosting_type": "gbdt",
        "learning_rate": 0.03,
        "num_leaves": 31,
        "max_depth": 5,
        "min_child_samples": 80,
        "colsample_bytree": 0.7,
        "subsample": 0.8,
        "subsample_freq": 1,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "n_jobs": -1,
        "seed": 42,
        "verbose": -1,
    }

    print("\nTraining LightGBM …")
    print(f"  Hyperparams: lr={params['learning_rate']}, "
          f"max_depth={params['max_depth']}, "
          f"min_child_samples={params['min_child_samples']}, "
          f"colsample_bytree={params['colsample_bytree']}")

    callbacks = [
        lgb.log_evaluation(period=25),
        lgb.early_stopping(stopping_rounds=EARLY_STOPPING_ROUNDS),
    ]

    model = lgb.train(
        params,
        ds_train,
        num_boost_round=3000,
        valid_sets=[ds_train, ds_val],
        valid_names=["train", "val"],
        callbacks=callbacks,
    )

    # ── Evaluation ───────────────────────────────────────────────
    best_iter = model.best_iteration
    best_score = model.best_score["val"]["l2"]
    print(f"\nBest iteration: {best_iter}")
    print(f"Best val MSE:   {best_score:.8f}")
    print(f"Best val RMSE:  {best_score ** 0.5:.8f}")

    y_pred = model.predict(X_val, num_iteration=best_iter)
    direction_acc = np.mean((y_pred > 0) == (y_val > 0))
    print(f"Directional accuracy (val): {direction_acc:.4f}")

    # ── Feature importance (Top 15) ──────────────────────────────
    importance = model.feature_importance(importance_type="gain")
    feat_imp = sorted(
        zip(col_names, importance), key=lambda x: x[1], reverse=True,
    )

    print("\n" + "=" * 52)
    print("  Top 15 Features by Gain")
    print("=" * 52)
    for rank, (name, score) in enumerate(feat_imp[:15], 1):
        bar = "█" * int(score / max(importance) * 30)
        print(f"  {rank:2d}. {name:<28s} {score:>10.1f}  {bar}")
    print("=" * 52)

    # ── Save model ───────────────────────────────────────────────
    model_path = SCRIPT_DIR / "lgbm_5d_return.txt"
    model.save_model(str(model_path), num_iteration=best_iter)
    print(f"\nModel saved → {model_path}")

    # ── Save feature importance to JSON for downstream use ───────
    import json

    imp_path = SCRIPT_DIR / "lgbm_feature_importance.json"
    imp_path.write_text(json.dumps(
        [{"feature": n, "gain": float(g)} for n, g in feat_imp],
        indent=2,
    ))
    print(f"Feature importance → {imp_path}")


if __name__ == "__main__":
    main()
