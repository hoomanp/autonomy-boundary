"""JEPA (Joint-Embedding Predictive Architecture) World-State Energy Control.

Inspired by LeCun's Joint-Embedding Predictive Architecture (I-JEPA / V-JEPA),
this control replaces slow, stochastic generative LLM rollouts at the autonomy
boundary with deterministic, sub-millisecond latent state prediction and
energy-based trajectory gating:

    1. State Encoder:      s_t      = E(x_t)          in R^d
    2. Action Predictor:   s^_{t+1} = P(s_t, a_t)     in R^d
    3. Safety Energy:      E(s_t, a_t, s^_{t+1}) <= tau

Where E combines:
    - Latent transition energy ||s^_{t+1} - s_t||_2^2 (abrupt state drift)
    - Safety manifold barrier energy max(0, ||s^_{t+1} - c_safe|| - r_safe)^2
    - Invariant constraint violation energy across semantic risk dimensions

Custom neural encoders/predictors (e.g., ONNX Runtime or PyTorch modules) can
be injected via `encoder_fn` and `predictor_fn`, while the default built-in
factored latent encoder/predictor operates in < 0.2ms with zero external deps.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from abf.controls.base import Control, ControlResult
from abf.intent import Intent

# Default 8-dimensional factored latent space:
# [0] financial_exposure   (normalized log-scale cumulative spend / transfer)
# [1] blast_radius         (scope of affected records / hosts / files)
# [2] privilege_elevation  (capability / identity sensitivity)
# [3] data_sensitivity     (confidentiality tier of data boundary)
# [4] destructiveness      (irreversibility / deletion / overwrite pressure)
# [5] external_egress      (network / external boundary crossing)
# [6] state_volatility     (churn / step frequency / mutation velocity)
# [7] semantic_coherent    (hash-projected contextual alignment dimension)
LATENT_DIM_NAMES: tuple[str, ...] = (
    "financial_exposure",
    "blast_radius",
    "privilege_elevation",
    "data_sensitivity",
    "destructiveness",
    "external_egress",
    "state_volatility",
    "semantic_coherence",
)


@dataclass(frozen=True)
class JEPAPrediction:
    """Result of encoding current state, predicting next latent state, and scoring energy."""

    s_t: tuple[float, ...]
    s_hat_next: tuple[float, ...]
    transition_energy: float
    barrier_energy: float
    total_energy: float
    threshold: float
    violated_dimensions: tuple[str, ...] = ()

    @property
    def admissible(self) -> bool:
        return self.total_energy <= self.threshold and not self.violated_dimensions


@dataclass
class LatentSafetyManifold:
    """Defines the safe operating region in latent space R^d.

    For each dimension i, `upper_bounds[i]` defines the maximum admissible
    coordinate before barrier energy spikes quadratically.
    """

    upper_bounds: tuple[float, ...] = (
        0.75,  # financial_exposure
        0.70,  # blast_radius
        0.75,  # privilege_elevation
        0.80,  # data_sensitivity
        0.65,  # destructiveness
        0.70,  # external_egress
        0.80,  # state_volatility
        1.00,  # semantic_coherence
    )
    barrier_stiffness: float = 4.0


def _clamp(val: float, lo: float = 0.0, hi: float = 2.0) -> float:
    return max(lo, min(hi, val))


def default_state_encoder(state: Mapping[str, Any]) -> tuple[float, ...]:
    """Encode observable environment state x_t into an 8-D latent vector s_t."""
    spend = float(state.get("cumulative_spend", state.get("amount_spent", 0.0)) or 0.0)
    budget_limit = float(state.get("budget_limit", 1000.0) or 1000.0)
    fin = _clamp(spend / max(budget_limit, 1.0))

    affected = float(state.get("affected_resources", state.get("touched_count", 0)) or 0.0)
    blast = _clamp(math.log1p(affected) / math.log1p(100.0))

    priv = float(state.get("privilege_level", 0.1) or 0.1)
    sensitivity = float(state.get("data_sensitivity", 0.2) or 0.2)
    destruct = float(state.get("destructiveness", 0.0) or 0.0)
    egress = float(state.get("external_egress", 0.0) or 0.0)
    volatility = float(state.get("state_volatility", 0.1) or 0.1)

    # Deterministic projection of discrete state keys for semantic coherence
    digest = hashlib.sha256(repr(sorted(state.items())).encode("utf-8")).digest()
    coherence = (digest[0] / 255.0) * 0.25

    return (
        round(fin, 6),
        round(blast, 6),
        round(_clamp(priv), 6),
        round(_clamp(sensitivity), 6),
        round(_clamp(destruct), 6),
        round(_clamp(egress), 6),
        round(_clamp(volatility), 6),
        round(coherence, 6),
    )


def default_action_predictor(
    s_t: Sequence[float],
    intent: Intent,
    state: Mapping[str, Any] | None = None,
) -> tuple[float, ...]:
    """Predict post-action latent vector s^_{t+1} = P(s_t, a_t) in R^8."""
    state = state or {}
    fin, blast, priv, sens, destruct, egress, vol, coh = (
        list(s_t) + [0.0] * 8
    )[:8]

    params = intent.params or {}
    action_lower = intent.action.lower()
    target_lower = intent.effect_target.lower()
    caps = {c.lower() for c in intent.capabilities}

    # 1. Financial delta
    amount = float(params.get("amount", params.get("cost", params.get("value", 0.0))) or 0.0)
    budget_limit = float(state.get("budget_limit", 1000.0) or 1000.0)
    fin_next = _clamp(fin + (amount / max(budget_limit, 1.0)))

    # 2. Blast radius delta
    batch_size = float(
        params.get("count", params.get("limit", params.get("batch_size", 1))) or 1.0
    )
    wildcard_penalty = 0.45 if ("*" in target_lower or "all" in params) else 0.0
    recursive_penalty = 0.35 if params.get("recursive") or params.get("force") else 0.0
    blast_next = _clamp(
        blast
        + (math.log1p(batch_size) / math.log1p(500.0)) * 0.5
        + wildcard_penalty
        + recursive_penalty
    )

    # 3. Privilege elevation delta
    high_priv_caps = {"admin", "root", "sudo", "iam:write", "secrets:read", " ledger:admin"}
    priv_delta = 0.15 * len(caps & high_priv_caps)
    if "admin" in (intent.effective_identity or "").lower() or "root" in (
        intent.effective_identity or ""
    ).lower():
        priv_delta += 0.35
    priv_next = _clamp(priv + priv_delta)

    # 4. Data sensitivity delta
    boundary_lower = (intent.data_boundary or "").lower()
    sens_delta = 0.0
    if any(k in boundary_lower for k in ("pii", "pci", "secret", "prod", "restricted", "hipaa")):
        sens_delta += 0.35
    if any(k in target_lower for k in ("/etc/", "passwd", ".env", "credentials", "prod")):
        sens_delta += 0.40
    sens_next = _clamp(max(sens, sens + sens_delta))

    # 5. Destructiveness delta
    destruct_verbs = ("delete", "drop", "destroy", "truncate", "wipe", "purge", "revoke", "kill")
    mutate_verbs = ("write", "update", "issue", "send", "post", "transfer", "exec")
    if any(v in action_lower for v in destruct_verbs):
        destruct_delta = 0.60 + recursive_penalty
    elif any(v in action_lower for v in mutate_verbs):
        destruct_delta = 0.20
    else:
        destruct_delta = 0.0
    destruct_next = _clamp(destruct + destruct_delta)

    # 6. External egress delta
    egress_delta = 0.0
    if any(v in action_lower for v in ("email", "webhook", "http", "export", "upload", "post")):
        egress_delta += 0.35
    if any(
        ext in target_lower
        for ext in ("http://", "https://", "@", "external", "0.0.0.0", "webhook")
    ):
        egress_delta += 0.35
    # High data sensitivity combined with external egress compounds risk
    if egress_delta > 0 and sens_next >= 0.55:
        egress_delta += 0.25
    egress_next = _clamp(egress + egress_delta)

    # 7. State volatility delta
    step_Penalty = 0.05 * max(0, int(intent.step_index))
    vol_next = _clamp(vol + 0.08 + step_Penalty)

    # 8. Semantic coherence shift
    coh_next = _clamp(coh + 0.05 * (destruct_delta + egress_delta))

    return (
        round(fin_next, 6),
        round(blast_next, 6),
        round(priv_next, 6),
        round(sens_next, 6),
        round(destruct_next, 6),
        round(egress_next, 6),
        round(vol_next, 6),
        round(coh_next, 6),
    )


class JEPAWorldStateControl(Control):
    """Control #8: Joint-Embedding Predictive Architecture World-State Energy Gate.

    Evaluates whether the predicted latent state transition s_t -> s^_{t+1}
    under `intent` remains within the low-energy safety manifold.
    """

    name = "jepa_world_state"

    def __init__(
        self,
        *,
        energy_threshold: float = 0.65,
        manifold: LatentSafetyManifold | None = None,
        transition_weight: float = 1.0,
        barrier_weight: float = 1.0,
        encoder_fn: Callable[[Mapping[str, Any]], Sequence[float]] | None = None,
        predictor_fn: Callable[
            [Sequence[float], Intent, Mapping[str, Any]], Sequence[float]
        ]
        | None = None,
        dimension_names: Sequence[str] = LATENT_DIM_NAMES,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.manifold = manifold or LatentSafetyManifold()
        self.transition_weight = transition_weight
        self.barrier_weight = barrier_weight
        self._encoder_fn = encoder_fn or default_state_encoder
        self._predictor_fn = predictor_fn or default_action_predictor
        self.dimension_names = tuple(dimension_names)

    def predict(
        self, intent: Intent, world_state: Mapping[str, Any] | None = None
    ) -> JEPAPrediction:
        """Encode current world state, predict post-action latent state, and compute energy."""
        state = dict(world_state or {})
        s_t = tuple(float(x) for x in self._encoder_fn(state))
        s_hat = tuple(float(x) for x in self._predictor_fn(s_t, intent, state))

        # 1. Transition energy: squared L2 norm ||s^_{t+1} - s_t||_2^2
        trans_energy = sum((b - a) ** 2 for a, b in zip(s_t, s_hat))

        # 2. Manifold barrier energy: penalize coordinates exceeding upper safety bounds
        barrier_energy = 0.0
        violated: list[str] = []
        bounds = self.manifold.upper_bounds
        for idx, val in enumerate(s_hat):
            bound = bounds[idx] if idx < len(bounds) else 1.0
            excess = max(0.0, val - bound)
            if excess > 0.0:
                barrier_energy += self.manifold.barrier_stiffness * (excess ** 2)
                dim_name = (
                    self.dimension_names[idx]
                    if idx < len(self.dimension_names)
                    else f"dim_{idx}"
                )
                violated.append(f"{dim_name}({val:.2f}>{bound:.2f})")

        total_energy = (
            self.transition_weight * trans_energy
            + self.barrier_weight * barrier_energy
        )

        return JEPAPrediction(
            s_t=s_t,
            s_hat_next=s_hat,
            transition_energy=round(trans_energy, 6),
            barrier_energy=round(barrier_energy, 6),
            total_energy=round(total_energy, 6),
            threshold=self.energy_threshold,
            violated_dimensions=tuple(violated),
        )

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        world_state = context.get("world_state") or context.get("current_state") or {}
        prediction = self.predict(intent, world_state)

        if not prediction.admissible:
            return self.deny(
                "predicted post-action world state exceeds JEPA safety energy threshold",
                energy=prediction.total_energy,
                threshold=prediction.threshold,
                transition_energy=prediction.transition_energy,
                barrier_energy=prediction.barrier_energy,
                violated_dimensions=list(prediction.violated_dimensions),
                s_t=list(prediction.s_t),
                s_hat_next=list(prediction.s_hat_next),
            )

        return self.allow(
            "predicted latent trajectory within safety manifold",
            energy=prediction.total_energy,
            threshold=prediction.threshold,
            s_hat_next=list(prediction.s_hat_next),
        )
