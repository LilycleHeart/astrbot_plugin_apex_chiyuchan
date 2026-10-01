"""Rolling RP summaries from observations, never from chart point count."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RPWindow:
    delta: int | None = None
    status: str = "insufficient"
    baseline_at: str | None = None

    @property
    def text(self) -> str:
        if self.delta is None:
            return "24h 暂无"
        arrow = "▲ " if self.delta > 0 else "▼ " if self.delta < 0 else ""
        estimate = "≈" if self.status == "estimated" else ""
        return f"{arrow}{estimate}{self.delta:+,} · 24h"


def calculate_rp_window(rows, current_score: int, now: datetime, rank_season=None) -> RPWindow:
    """Use the last observation at/before the cutoff, at most 6h older.

    Rows must be newest first (recorded_at, then id), including observations
    after the cutoff so known season changes anywhere in the window are caught.
    Times deliberately keep the legacy database's server-local semantics.
    No interpolation, extrapolation across long gaps, or loss-as-reset heuristic.
    """
    cutoff = now - timedelta(hours=24)
    known_seasons = {rank_season} if rank_season else set()
    for row in rows:
        try:
            at = datetime.strptime(row["recorded_at"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        if not cutoff - timedelta(hours=6) <= at <= now:
            continue
        baseline_season = row["rank_season"]
        if baseline_season:
            known_seasons.add(baseline_season)
        if at > cutoff:
            continue
        if len(known_seasons) > 1:
            return RPWindow(status="reset", baseline_at=row["recorded_at"])
        return RPWindow(
            delta=current_score - row["rank_score"],
            # Legacy rows have no season metadata. Keep their score/time usable
            # without assigning today's season to them or claiming certainty.
            status="exact" if at == cutoff and rank_season and baseline_season else "estimated",
            baseline_at=row["recorded_at"],
        )
    return RPWindow()
