from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Room:
    id: Optional[int]
    name: str
    default_rent: float
    is_occupied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        return cls(
            id=data.get("id"),
            name=data["name"],
            default_rent=float(data["default_rent"]),
            is_occupied=bool(data.get("is_occupied", False))
        )


@dataclass
class Lease:
    id: Optional[int]
    room_id: int
    tenant_name: str
    tenant_phone: str
    monthly_rent: float
    start_date: str  # ISO YYYY-MM-DD
    end_date: Optional[str] = None  # ISO YYYY-MM-DD
    is_active: bool = True
    deposit_amount: float = 0.0
    initial_rent: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Lease":
        return cls(
            id=data.get("id"),
            room_id=int(data["room_id"]),
            tenant_name=data["tenant_name"],
            tenant_phone=data["tenant_phone"],
            monthly_rent=float(data["monthly_rent"]),
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            is_active=bool(data.get("is_active", True)),
            deposit_amount=float(data.get("deposit_amount", 0.0)),
            initial_rent=float(data["initial_rent"]) if data.get("initial_rent") is not None else None
        )


@dataclass
class Payment:
    id: Optional[int]
    lease_id: int
    billing_year: int
    billing_month: int
    amount: float
    paid_date: str  # ISO YYYY-MM-DD
    proof_image_path: Optional[str] = None
    payment_method: str = "TRANSFERENCIA"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Payment":
        return cls(
            id=data.get("id"),
            lease_id=int(data["lease_id"]),
            billing_year=int(data["billing_year"]),
            billing_month=int(data["billing_month"]),
            amount=float(data["amount"]),
            paid_date=data["paid_date"],
            proof_image_path=data.get("proof_image_path"),
            payment_method=data.get("payment_method", "TRANSFERENCIA")
        )
