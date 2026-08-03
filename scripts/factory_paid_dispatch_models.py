from __future__ import annotations

from dataclasses import dataclass


class PaidDispatchError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class PaidDispatchReservation:
    authorization_id: str
    reservation_id: str | None
    held_microcents: int
    provider_lane_id: str
    provider_id: str
    model_id: str | None
    requested_model: str

    def job_projection(self) -> dict[str, object]:
        projection: dict[str, object] = {
            "dispatch_authorization_id": self.authorization_id,
            "settlement_state": "unresolved",
            "cost_provider_lane_id": self.provider_lane_id,
            "cost_provider_id": self.provider_id,
            "cost_model_id": self.model_id,
            "reserved_microcents": self.held_microcents,
        }
        if self.reservation_id is not None:
            projection["reservation_id"] = self.reservation_id
        return projection
