"""
QuantModel — Hybrid Temporal Multi-Task Network for the Global Panel Model.

Architecture:
    ticker_id          →  nn.Embedding       →  ┐
    temporal_features  →  2-layer LSTM        →  ├─ concat → Shared MLP → ┬─ return_head    (regression)
    external_features  →  Linear + ReLU (opt) →  ┘                        ├─ direction_head  (binary clf)
                                                                          └─ volatility_head (positive reg)
"""
import json
from pathlib import Path
from typing import NamedTuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ──────────────────────────────────────────────────────────────────────
# Structured output
# ──────────────────────────────────────────────────────────────────────

class QuantModelOutput(NamedTuple):
    pred_return: torch.Tensor      # (B,) predicted 5-day return
    pred_direction: torch.Tensor   # (B,) logit for up / down
    pred_volatility: torch.Tensor  # (B,) predicted volatility (≥ 0)


# ──────────────────────────────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────────────────────────────

class QuantModel(nn.Module):
    """Hybrid Temporal Multi-Task Network.

    Combines a per-ticker embedding, a 2-layer LSTM for temporal
    feature sequences, and an optional external-feature branch.
    The fused representation feeds three task-specific heads.
    """

    def __init__(
        self,
        num_features: int,
        num_embeddings: int,
        embed_dim: int = 16,
        lstm_hidden: int = 32,
        lstm_layers: int = 2,
        lstm_dropout: float = 0.3,
        num_ext_features: int = 0,
        ext_hidden: int = 16,
        shared_dims: list[int] | None = None,
        dropout: float = 0.1,
    ) -> None:
        """
        Args:
            num_features: Technical-indicator count per timestep.
            num_embeddings: Ticker vocabulary size (inc. <UNK>).
            embed_dim: Ticker embedding dimensionality.
            lstm_hidden: LSTM hidden size.
            lstm_layers: Stacked LSTM layers.
            lstm_dropout: Inter-layer LSTM dropout (ignored when layers=1).
            num_ext_features: External-feature dim (0 = branch disabled).
            ext_hidden: Projection size for external features.
            shared_dims: Hidden sizes for the fusion MLP.
            dropout: Dropout rate in the fusion MLP.
        """
        super().__init__()
        shared_dims = shared_dims or [32, 16]
        self.num_ext_features = num_ext_features

        # ── Entity branch ────────────────────────────────────────
        self.ticker_embedding = nn.Embedding(
            num_embeddings, embed_dim, padding_idx=0,
        )

        # ── Temporal branch ──────────────────────────────────────
        self.lstm = nn.LSTM(
            input_size=num_features,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            dropout=lstm_dropout if lstm_layers > 1 else 0.0,
        )
        self.temporal_ln = nn.LayerNorm(lstm_hidden)

        # ── External branch (optional) ───────────────────────────
        if num_ext_features > 0:
            self.ext_proj = nn.Sequential(
                nn.Linear(num_ext_features, ext_hidden),
                nn.ReLU(),
            )
            ext_out_dim = ext_hidden
        else:
            self.ext_proj = None
            ext_out_dim = 0

        # ── Shared fusion MLP ────────────────────────────────────
        fused_dim = embed_dim + lstm_hidden + ext_out_dim
        layers: list[nn.Module] = []
        in_dim = fused_dim
        for h in shared_dims:
            layers += [
                nn.Linear(in_dim, h),
                nn.BatchNorm1d(h),
                nn.GELU(),
                nn.Dropout(dropout),
            ]
            in_dim = h
        self.shared_mlp = nn.Sequential(*layers)

        # ── Task heads ───────────────────────────────────────────
        head_in = shared_dims[-1]
        self.return_head = nn.Linear(head_in, 1)
        self.direction_head = nn.Linear(head_in, 1)
        self.volatility_head = nn.Sequential(
            nn.Linear(head_in, 1),
            nn.Softplus(),
        )

        # ── Learnable uncertainty weights (Kendall et al.) ────
        self.log_var_ret = nn.Parameter(torch.zeros(1))
        self.log_var_dir = nn.Parameter(torch.zeros(1))
        self.log_var_vol = nn.Parameter(torch.zeros(1))

    # ── forward ──────────────────────────────────────────────────
    def forward(
        self,
        ticker_ids: torch.Tensor,
        temporal_features: torch.Tensor,
        external_features: torch.Tensor | None = None,
    ) -> QuantModelOutput:
        """
        Args:
            ticker_ids: (B,) long — ticker vocabulary IDs.
            temporal_features: (B, seq_len, num_features) float.
            external_features: (B, num_ext_features) float | None.

        Returns:
            QuantModelOutput with pred_return, pred_direction,
            pred_volatility — each of shape (B,).
        """
        emb = self.ticker_embedding(ticker_ids)              # (B, E)

        lstm_out, _ = self.lstm(temporal_features)            # (B, S, H)
        temporal = self.temporal_ln(lstm_out.mean(dim=1))      # (B, H)

        branches = [emb, temporal]
        if self.ext_proj is not None and external_features is not None:
            branches.append(self.ext_proj(external_features))

        shared = self.shared_mlp(torch.cat(branches, dim=1))

        return QuantModelOutput(
            pred_return=self.return_head(shared).squeeze(-1),
            pred_direction=self.direction_head(shared).squeeze(-1),
            pred_volatility=self.volatility_head(shared).squeeze(-1),
        )

    # ── loss (Kendall et al. dynamic uncertainty weighting) ──────
    def compute_loss(
        self,
        output: QuantModelOutput,
        true_return: torch.Tensor,
        true_volatility: torch.Tensor,
        true_direction: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        """Multi-task loss with learned per-task precision.

        Each head's raw loss is scaled by a learned inverse-variance
        (precision) term:  ``L = loss * exp(-s) + s``  where
        ``s = log(sigma^2)``.  The network learns to down-weight
        noisy tasks automatically (Kendall et al., 2018).

        Args:
            output: Model predictions.
            true_return: (B,) ground-truth 5-day forward return
                (may be Z-scored).
            true_volatility: (B,) ground-truth 5-day realized volatility
                (may be Z-scored).
            true_direction: (B,) binary direction labels (0/1).
                If *None*, falls back to ``(true_return > 0)`` — only
                valid when returns are NOT Z-scored.

        Returns:
            (total_loss, breakdown dict with raw losses & learned weights)
        """
        l_ret = F.mse_loss(output.pred_return, true_return)

        if true_direction is None:
            true_direction = (true_return > 0).float()
        l_dir = F.binary_cross_entropy_with_logits(
            output.pred_direction, true_direction,
        )

        l_vol = F.huber_loss(
            output.pred_volatility, true_volatility, delta=1.0,
        )

        total = (
            l_ret * torch.exp(-self.log_var_ret) + self.log_var_ret
            + l_dir * torch.exp(-self.log_var_dir) + self.log_var_dir
            + l_vol * torch.exp(-self.log_var_vol) + self.log_var_vol
        ).squeeze()

        return total, {
            "return": l_ret.item(),
            "direction": l_dir.item(),
            "volatility": l_vol.item(),
            "total": total.item(),
            "w_ret": torch.exp(-self.log_var_ret).item(),
            "w_dir": torch.exp(-self.log_var_dir).item(),
            "w_vol": torch.exp(-self.log_var_vol).item(),
        }


# ──────────────────────────────────────────────────────────────────────
# Singleton model manager (inference) — supports QuantModel + LightGBM
# ──────────────────────────────────────────────────────────────────────

class ModelManager:
    """Singleton that caches loaded models and dispatches inference by name.

    Supported backends:
        ``"quant"``  — PyTorch QuantModel (LSTM multi-task)
        ``"lgbm"``   — LightGBM Booster (gradient-boosted trees)
    """

    QUANT = "quant"
    LGBM = "lgbm"

    _instance: "ModelManager | None" = None

    def __new__(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._models: dict = {}
            cls._instance._vocab: dict | None = None
            cls._instance._feat_mean = None
            cls._instance._feat_std = None
            cls._instance._device = "cpu"
        return cls._instance

    # ── loaders ───────────────────────────────────────────────────

    def _ensure_vocab(self, vocab_path: str | Path) -> None:
        if self._vocab is None:
            with open(vocab_path) as f:
                self._vocab = json.load(f)

    def load_quant(
        self,
        weights_path: str | Path,
        vocab_path: str | Path,
        norm_path: str | Path,
        device: str = "cpu",
        **model_kwargs,
    ) -> None:
        """Load the PyTorch QuantModel.

        Args:
            weights_path: Path to ``global_alpha.pth``.
            vocab_path: Path to ``ticker_vocab.json``.
            norm_path: Path to ``feat_norm.pt``.
            device: ``'cpu'``, ``'mps'``, or ``'cuda'``.
            **model_kwargs: Extra kwargs forwarded to QuantModel.
        """
        from .features import FEATURE_COLS

        self._ensure_vocab(vocab_path)

        cfg = {
            "num_features": len(FEATURE_COLS),
            "num_embeddings": len(self._vocab),
        }
        cfg.update(model_kwargs)

        model = QuantModel(**cfg)
        state = torch.load(
            str(weights_path), map_location=device, weights_only=True,
        )
        model.load_state_dict(state)
        model.to(device)
        model.eval()

        norm = torch.load(
            str(norm_path), map_location=device, weights_only=True,
        )
        self._feat_mean = norm["mean"].to(device)
        self._feat_std = norm["std"].to(device)
        self._device = device
        self._models[self.QUANT] = model

    def load_lgbm(
        self,
        model_path: str | Path,
        vocab_path: str | Path | None = None,
    ) -> None:
        """Load a LightGBM Booster from its text file.

        Args:
            model_path: Path to ``lgbm_5d_return.txt``.
            vocab_path: Path to ``ticker_vocab.json``.  Optional if
                the vocab was already loaded by :meth:`load_quant`.
        """
        import lightgbm as lgb

        if vocab_path is not None:
            self._ensure_vocab(vocab_path)

        self._models[self.LGBM] = lgb.Booster(model_file=str(model_path))

    # ── properties ────────────────────────────────────────────────

    @property
    def available_models(self) -> list[str]:
        return list(self._models.keys())

    @property
    def vocab(self) -> dict[str, int]:
        if self._vocab is None:
            raise RuntimeError("Vocab not loaded. Call load_quant/load_lgbm with vocab_path first.")
        return self._vocab

    @property
    def device(self) -> str:
        return self._device

    def get_model(self, name: str):
        """Return the raw model object by name."""
        if name not in self._models:
            raise RuntimeError(
                f"Model '{name}' not loaded. Available: {self.available_models}"
            )
        return self._models[name]

    # ── shared helpers ────────────────────────────────────────────

    def normalize(self, features: torch.Tensor) -> torch.Tensor:
        """Apply train-set normalization (QuantModel only).  Broadcasts
        correctly for both (B, F) and (B, seq_len, F) shaped inputs."""
        return (features - self._feat_mean) / self._feat_std

    def ticker_to_id(self, ticker: str) -> int:
        """Map a ticker to its vocab ID, falling back to <UNK>."""
        return self.vocab.get(ticker, self.vocab["<UNK>"])

    @staticmethod
    def _flatten_for_lgbm(features_3d: np.ndarray) -> np.ndarray:
        """(B, seq_len, F) → (B, 3*F)  via last / mean / std."""
        last = features_3d[:, -1, :]
        mean = features_3d.mean(axis=1)
        std = features_3d.std(axis=1)
        return np.concatenate([last, mean, std], axis=1)

    # ── unified predict ───────────────────────────────────────────

    def predict(
        self,
        name: str,
        ticker: str,
        temporal_features: np.ndarray,
        external_features: np.ndarray | None = None,
    ) -> dict:
        """Run inference on a named model.

        Args:
            name: ``"quant"`` or ``"lgbm"``.
            ticker: Ticker symbol (e.g. ``"AAPL"``).
            temporal_features: ``(seq_len, F)`` or ``(B, seq_len, F)``
                raw (un-normalized) feature array.
            external_features: Optional ``(B, E)`` array for QuantModel's
                external branch.  Ignored by LightGBM.

        Returns:
            dict with ``pred_return`` (always present) and, for the quant
            model, ``pred_direction`` and ``pred_volatility``.
        """
        model = self.get_model(name)

        if temporal_features.ndim == 2:
            temporal_features = temporal_features[np.newaxis]  # (1, S, F)

        if name == self.QUANT:
            return self._predict_quant(
                model, ticker, temporal_features, external_features,
            )
        if name == self.LGBM:
            return self._predict_lgbm(model, temporal_features)

        raise ValueError(f"Unknown model name: '{name}'")

    def _predict_quant(
        self,
        model: QuantModel,
        ticker: str,
        features: np.ndarray,
        external: np.ndarray | None,
    ) -> dict:
        tid = torch.tensor([self.ticker_to_id(ticker)], device=self._device)
        feat_t = torch.from_numpy(features).float().to(self._device)
        feat_t = self.normalize(feat_t)

        ext_t = None
        if external is not None:
            ext_t = torch.from_numpy(external).float().to(self._device)

        with torch.no_grad():
            out = model(tid.expand(feat_t.shape[0]), feat_t, ext_t)

        return {
            "model": self.QUANT,
            "pred_return": out.pred_return.cpu().numpy().tolist(),
            "pred_direction": torch.sigmoid(out.pred_direction).cpu().numpy().tolist(),
            "pred_volatility": out.pred_volatility.cpu().numpy().tolist(),
        }

    def _predict_lgbm(
        self,
        booster,
        features: np.ndarray,
    ) -> dict:
        X = self._flatten_for_lgbm(features.astype(np.float64))
        preds = booster.predict(X).tolist()
        return {
            "model": self.LGBM,
            "pred_return": preds,
        }


# ──────────────────────────────────────────────────────────────────────
# Smoke test
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    B, SEQ, FEAT = 32, 20, 10
    NUM_EMB = 100
    EXT_F = 4

    ids = torch.randint(1, NUM_EMB, (B,))
    temporal = torch.randn(B, SEQ, FEAT)

    print("=" * 50)
    print("  QuantModel — Shape Verification")
    print("=" * 50)

    # ── Without external features ────────────────────────────────
    model = QuantModel(num_features=FEAT, num_embeddings=NUM_EMB)
    out = model(ids, temporal)

    print(f"\n[no ext]  pred_return:     {out.pred_return.shape}")
    print(f"[no ext]  pred_direction:  {out.pred_direction.shape}")
    print(f"[no ext]  pred_volatility: {out.pred_volatility.shape}")
    assert out.pred_return.shape == (B,)
    assert out.pred_direction.shape == (B,)
    assert out.pred_volatility.shape == (B,)
    assert (out.pred_volatility >= 0).all(), "Softplus must produce ≥ 0"

    # ── With external features ───────────────────────────────────
    model_ext = QuantModel(
        num_features=FEAT, num_embeddings=NUM_EMB,
        num_ext_features=EXT_F,
    )
    ext = torch.randn(B, EXT_F)
    out_ext = model_ext(ids, temporal, ext)

    print(f"\n[w/ ext]  pred_return:     {out_ext.pred_return.shape}")
    print(f"[w/ ext]  pred_direction:  {out_ext.pred_direction.shape}")
    print(f"[w/ ext]  pred_volatility: {out_ext.pred_volatility.shape}")
    assert out_ext.pred_return.shape == (B,)

    # ── compute_loss (uncertainty-weighted) ──────────────────────
    true_ret = torch.randn(B)
    true_vol = torch.rand(B)
    loss, breakdown = model.compute_loss(out, true_ret, true_vol)

    print(f"\nMulti-task loss: {loss.item():.4f}")
    for k, v in breakdown.items():
        print(f"  {k:>12s}: {v:.4f}")

    # ── Param count ──────────────────────────────────────────────
    total_p = sum(p.numel() for p in model.parameters())
    train_p = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nParams — total: {total_p:,}  trainable: {train_p:,}")

    print("\n✓  All shape assertions passed.")
