from dataclasses import dataclass
from enum import StrEnum


class UserRole(StrEnum):
    customer = "customer"
    expert_review = "expert_review"
    admin = "admin"


@dataclass
class User:
    id: str
    email: str
    report_count: int = 0
    role: UserRole = UserRole.customer
    preferred_language: str = "en"
