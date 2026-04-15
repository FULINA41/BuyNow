"""
Training loop for the QuantModel (Hybrid Temporal Multi-Task Network).
Enforces strict chronological Time-Series Split to prevent lookahead bias.

Run from the backend/ directory:
    python -m train.trainer
"""
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import torch
import torch.nn as nn
from dotenv import load_dotenv
from torch.utils.data import DataLoader, Dataset

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
from app.ml.features import FEATURE_COLS  # noqa: E402
from app.ml.model import QuantModel  # noqa: E402

TARGET_COL = "fwd_ret_5d"
VOL_COL = "fwd_vol_5d"
SEQ_LEN = 20
EPOCHS = 50
BATCH_SIZE = 4096
LR = 1e-2
WEIGHT_DECAY = 1e-4
TRAIN_RATIO = 0.8


# ── Dataset ──────────────────────────────────────────────────────────

class SequenceDataset(Dataset):
    """Serves (features, ticker_id, ret, vol, direction) tuples."""

    def __init__(
        self,
        features: torch.Tensor,
        ticker_ids: torch.Tensor,
        ret_targets: torch.Tensor,
        vol_targets: torch.Tensor,
        dir_targets: torch.Tensor,
    ) -> None:
        self.features = features        # (N, seq_len, F)
        self.ticker_ids = ticker_ids    # (N,)
        self.ret_targets = ret_targets  # (N,)
        self.vol_targets = vol_targets  # (N,)
        self.dir_targets = dir_targets  # (N,) binary 0/1

    def __len__(self) -> int:
        return len(self.ret_targets)

    def __getitem__(self, idx: int):
        return (
            self.features[idx],
            self.ticker_ids[idx],
            self.ret_targets[idx],
            self.vol_targets[idx],
            self.dir_targets[idx],
        )


# ── Helpers ──────────────────────────────────────────────────────────

def _select_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _add_vol_target(df: pl.DataFrame) -> pl.DataFrame:
    """Compute 5-day forward realized volatility (std of next 5 daily returns)."""
    df = df.sort("ticker", "date")
    df = df.with_columns(
        pl.col("returns")
        .rolling_std(window_size=5)
        .over("ticker")
        .alias("_rstd5"),
    )
    df = df.with_columns(
        pl.col("_rstd5").shift(-5).over("ticker").alias(VOL_COL),
    ).drop("_rstd5")
    return df


def _build_sequences(
    df: pl.DataFrame,
    seq_len: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build sliding-window sequences from sorted panel data.

    Returns:
        features   (N, seq_len, num_features) float32
        ticker_ids (N,) int64
        ret_targets(N,) float32
        vol_targets(N,) float32
        dates      (N,) datetime64
    """
    feat_arrs: list[np.ndarray] = []
    id_arrs: list[np.ndarray] = []
    ret_arrs: list[np.ndarray] = []
    vol_arrs: list[np.ndarray] = []
    date_arrs: list[np.ndarray] = []

    for group in df.partition_by("ticker", maintain_order=True):
        n = len(group)
        if n < seq_len:
            continue

        feat = group.select(FEATURE_COLS).to_numpy().astype(np.float32)
        ids = group["ticker_id"].to_numpy().astype(np.int64)
        ret = group[TARGET_COL].to_numpy().astype(np.float32)
        vol = group[VOL_COL].to_numpy().astype(np.float32)
        dates = group["date"].to_numpy()

        # (n - seq_len + 1, F, seq_len) → transpose → (n_win, seq_len, F)
        windows = np.lib.stride_tricks.sliding_window_view(
            feat, seq_len, axis=0,
        )
        windows = np.ascontiguousarray(windows.transpose(0, 2, 1))

        # windows[i] covers feat[i : i+seq_len]; target aligns to i+seq_len-1
        t = seq_len - 1
        feat_arrs.append(windows)
        id_arrs.append(ids[t:])
        ret_arrs.append(ret[t:])
        vol_arrs.append(vol[t:])
        date_arrs.append(dates[t:])

    return (
        np.concatenate(feat_arrs),
        np.concatenate(id_arrs),
        np.concatenate(ret_arrs),
        np.concatenate(vol_arrs),
        np.concatenate(date_arrs),
    )


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")
    device = _select_device()
    print(f"Device: {device}")

    # ── Load panel data ──────────────────────────────────────────
    parquet_path = SCRIPT_DIR / "panel_data.parquet"
    df = pl.read_parquet(str(parquet_path))
    print(f"Loaded {len(df):,} rows")

    # ── Add volatility target & clean ────────────────────────────
    df = _add_vol_target(df)
    df = df.drop_nulls(subset=[VOL_COL])

    # ── Build sliding-window sequences ───────────────────────────
    print(f"Building {SEQ_LEN}-day sliding windows …")
    features, ticker_ids, ret_targets, vol_targets, dates = (
        _build_sequences(df, SEQ_LEN)
    )
    print(f"  → {len(features):,} sequences")

    # ── Strict chronological split (by target date) ──────────────
    unique_dates = np.unique(dates)
    unique_dates.sort()
    split_date = unique_dates[int(len(unique_dates) * TRAIN_RATIO)]

    train_mask = dates < split_date
    val_mask = ~train_mask

    train_feat, val_feat = features[train_mask], features[val_mask]
    train_ids, val_ids = ticker_ids[train_mask], ticker_ids[val_mask]
    train_ret, val_ret = ret_targets[train_mask], ret_targets[val_mask]
    train_vol, val_vol = vol_targets[train_mask], vol_targets[val_mask]

    print(f"Train: {len(train_feat):,}   Val: {len(val_feat):,}")

    # ── Normalize features (fit on train only) ───────────────────
    feat_mean = train_feat.mean(axis=(0, 1)).astype(np.float32)   # (F,)
    feat_std = train_feat.std(axis=(0, 1)).astype(np.float32)
    feat_std = np.clip(feat_std, 1e-8, None)

    train_feat = (train_feat - feat_mean) / feat_std
    val_feat = (val_feat - feat_mean) / feat_std

    torch.save(
        {"mean": torch.from_numpy(feat_mean), "std": torch.from_numpy(feat_std)},
        str(SCRIPT_DIR / "feat_norm.pt"),
    )

    # ── Z-score normalize continuous targets (fit on train only) ─
    # Direction labels must be derived from RAW returns BEFORE normalization
    train_dir = (train_ret > 0).astype(np.float32)
    val_dir = (val_ret > 0).astype(np.float32)

    ret_mean = float(train_ret.mean())
    ret_std = float(np.clip(train_ret.std(), 1e-8, None))
    vol_mean = float(train_vol.mean())
    vol_std = float(np.clip(train_vol.std(), 1e-8, None))

    train_ret = ((train_ret - ret_mean) / ret_std).astype(np.float32)
    val_ret = ((val_ret - ret_mean) / ret_std).astype(np.float32)
    train_vol = ((train_vol - vol_mean) / vol_std).astype(np.float32)
    val_vol = ((val_vol - vol_mean) / vol_std).astype(np.float32)

    torch.save(
        {
            "ret_mean": torch.tensor(ret_mean),
            "ret_std": torch.tensor(ret_std),
            "vol_mean": torch.tensor(vol_mean),
            "vol_std": torch.tensor(vol_std),
        },
        str(SCRIPT_DIR / "target_norm.pt"),
    )
    print(
        f"  Target Z-score → ret μ={ret_mean:.6f} σ={ret_std:.6f}  "
        f"vol μ={vol_mean:.6f} σ={vol_std:.6f}"
    )

    # ── DataLoaders ──────────────────────────────────────────────
    train_loader = DataLoader(
        SequenceDataset(
            torch.from_numpy(train_feat),
            torch.from_numpy(train_ids),
            torch.from_numpy(train_ret),
            torch.from_numpy(train_vol),
            torch.from_numpy(train_dir),
        ),
        batch_size=BATCH_SIZE,
        shuffle=True,
    )
    val_loader = DataLoader(
        SequenceDataset(
            torch.from_numpy(val_feat),
            torch.from_numpy(val_ids),
            torch.from_numpy(val_ret),
            torch.from_numpy(val_vol),
            torch.from_numpy(val_dir),
        ),
        batch_size=BATCH_SIZE,
    )

    # ── Model / optimizer ────────────────────────────────────────
    vocab_path = SCRIPT_DIR / "ticker_vocab.json"
    with open(vocab_path) as f:
        num_embeddings = len(json.load(f))

    model = QuantModel(
        num_features=len(FEATURE_COLS),
        num_embeddings=num_embeddings,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    print(f"QuantModel — {n_params:,} params")

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=EPOCHS,
    )
    best_val_loss = float("inf")

    # ── Training loop ────────────────────────────────────────────
    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_sum = 0.0
        for feat, ids, ret, vol, dir_label in train_loader:
            feat, ids = feat.to(device), ids.to(device)
            ret, vol = ret.to(device), vol.to(device)
            dir_label = dir_label.to(device)

            optimizer.zero_grad()
            loss, _ = model.compute_loss(model(ids, feat), ret, vol, dir_label)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_sum += loss.item() * len(ret)
        scheduler.step()

        model.eval()
        val_sum = 0.0
        val_bd = {"return": 0.0, "direction": 0.0, "volatility": 0.0}
        with torch.no_grad():
            for feat, ids, ret, vol, dir_label in val_loader:
                feat, ids = feat.to(device), ids.to(device)
                ret, vol = ret.to(device), vol.to(device)
                dir_label = dir_label.to(device)
                loss, bd = model.compute_loss(
                    model(ids, feat), ret, vol, dir_label,
                )
                n = len(ret)
                val_sum += loss.item() * n
                for k in val_bd:
                    val_bd[k] += bd[k] * n

        train_loss = train_sum / len(train_feat)
        val_loss = val_sum / len(val_feat)
        for k in val_bd:
            val_bd[k] /= len(val_feat)

        tag = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(
                model.state_dict(), str(SCRIPT_DIR / "global_alpha.pth"),
            )
            tag = " ← saved"

        w_r = torch.exp(-model.log_var_ret).item()
        w_d = torch.exp(-model.log_var_dir).item()
        w_v = torch.exp(-model.log_var_vol).item()

        print(
            f"Epoch {epoch:3d}/{EPOCHS}  "
            f"train={train_loss:.6f}  val={val_loss:.6f}  "
            f"[ret={val_bd['return']:.4f} "
            f"dir={val_bd['direction']:.4f} "
            f"vol={val_bd['volatility']:.4f}]  "
            f"w=[{w_r:.2f} {w_d:.2f} {w_v:.2f}]"
            f"{tag}"
        )

    print(f"\nBest val loss: {best_val_loss:.6f}")
    print(
        f"Artifacts: {SCRIPT_DIR / 'global_alpha.pth'}, "
        f"{SCRIPT_DIR / 'feat_norm.pt'}, "
        f"{SCRIPT_DIR / 'target_norm.pt'}"
    )


if __name__ == "__main__":
    main()
