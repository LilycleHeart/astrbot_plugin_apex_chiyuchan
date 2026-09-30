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
            reason = {
                "reset": "赛季/分区已重置",
                "season_unknown": "缺少同赛季基准",
            }.get(self.status, "历史不足")
            return f"24h净变化：{reason}"
        prefix = "24h净变化（估算）" if self.status == "estimated" else "24h净变化"
        return f"{prefix} {self.delta:+,} RP"


def calculate_rp_window(rows, current_score: int, now: datetime, rank_season=None) -> RPWindow:
    """Use the last observation at/before the cutoff, at most 6h older.

    Times deliberately keep the legacy database's server-local semantics.
    No interpolation, extrapolation across long gaps, or loss-as-reset heuristic.
    """
    cutoff = now - timedelta(hours=24)
    for row in rows:
        try:
            at = datetime.strptime(row["recorded_at"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        if not cutoff - timedelta(hours=6) <= at <= cutoff:
            continue
        baseline_season = row["rank_season"]
        if rank_season != baseline_season:
            status = "reset" if rank_season and baseline_season else "season_unknown"
            return RPWindow(status=status, baseline_at=row["recorded_at"])
        return RPWindow(
            delta=current_score - row["rank_score"],
            status="exact" if at == cutoff else "estimated",
            baseline_at=row["recorded_at"],
        )
    return RPWindow()
