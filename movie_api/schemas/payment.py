from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    """A payment attempt submitted to confirm a reservation's hold."""

    amount: Decimal = Field(..., gt=0)
    provider_reference: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(
        json_schema_extra={"example": {"amount": "12.50", "provider_reference": "tok_visa"}}
    )
