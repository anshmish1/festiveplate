from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator, model_validator
from typing_extensions import Annotated

from .services.timegeo import to_naive_utc


def _ser_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_ser_utc, return_type=str)]

Role = Literal["DONOR", "NGO", "VOLUNTEER", "ADMIN"]
Language = Literal["en", "kn", "hi"]
DonorType = Literal["WEDDING_HALL", "RESTAURANT", "HOTEL", "CATERER", "EVENT_ORGANIZER", "HOUSEHOLD", "OTHER"]
FoodCategory = Literal["VEG", "NON_VEG", "EGG", "MIXED"]
Storage = Literal["HOT_HELD", "REFRIGERATED", "ROOM_TEMPERATURE", "FROZEN"]

Phone = Annotated[str, Field(pattern=r"^\+?[0-9 \-]{8,16}$")]
Lat = Annotated[float, Field(ge=-90, le=90)]
Lng = Annotated[float, Field(ge=-180, le=180)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class DonorRegistration(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    donor_type: DonorType
    address: str = Field(min_length=5, max_length=300)
    area: str = Field(min_length=2, max_length=100)
    latitude: Lat
    longitude: Lng


class NgoRegistration(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    registration_number: str = Field(min_length=3, max_length=80)
    contact_person: str = Field(min_length=2, max_length=120)
    address: str = Field(min_length=5, max_length=300)
    area: str = Field(min_length=2, max_length=100)
    latitude: Lat
    longitude: Lng
    service_radius_km: float = Field(gt=0, le=100, default=10)
    daily_capacity_portions: int = Field(gt=0, le=100000, default=200)
    accepts_veg: bool = True
    accepts_non_veg: bool = True
    pickup_start_hour: int = Field(ge=0, le=23, default=0)
    pickup_end_hour: int = Field(ge=0, le=24, default=24)
    has_vehicle: bool = False


class VolunteerRegistration(BaseModel):
    ngo_id: int
    vehicle_type: Optional[str] = Field(default=None, max_length=40)
    area: Optional[str] = Field(default=None, max_length=100)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: Optional[Phone] = None
    role: Literal["DONOR", "NGO", "VOLUNTEER"]
    preferred_language: Language = "en"
    donor: Optional[DonorRegistration] = None
    ngo: Optional[NgoRegistration] = None
    volunteer: Optional[VolunteerRegistration] = None

    @field_validator("password")
    @classmethod
    def _strong(cls, v: str) -> str:
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter and one digit")
        return v

    @model_validator(mode="after")
    def _profile_matches_role(self) -> "RegisterRequest":
        needed = {"DONOR": self.donor, "NGO": self.ngo, "VOLUNTEER": self.volunteer}[self.role]
        if needed is None:
            raise ValueError(f"{self.role.lower()} profile details are required for role {self.role}")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: Role
    preferred_language: Language
    notify_in_app: bool
    notify_sms: bool
    is_active: bool
    is_demo: bool
    created_at: UTCDateTime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SettingsUpdate(BaseModel):
    preferred_language: Optional[Language] = None
    notify_in_app: Optional[bool] = None
    notify_sms: Optional[bool] = None
    phone: Optional[Phone] = None
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)


# ---------- Profiles ----------
class DonorProfileOut(ORM):
    id: int
    organization_name: str
    donor_type: str
    address: str
    area: str
    latitude: float
    longitude: float


class NgoProfileOut(ORM):
    id: int
    user_id: int
    organization_name: str
    registration_number: str
    contact_person: str
    address: str
    area: str
    latitude: float
    longitude: float
    service_radius_km: float
    daily_capacity_portions: int
    accepts_veg: bool
    accepts_non_veg: bool
    pickup_start_hour: int
    pickup_end_hour: int
    has_vehicle: bool
    verification_status: str
    verification_notes: Optional[str]
    verified_at: Optional[UTCDateTime]
    created_at: UTCDateTime


class NgoProfileUpdate(BaseModel):
    service_radius_km: Optional[float] = Field(default=None, gt=0, le=100)
    daily_capacity_portions: Optional[int] = Field(default=None, gt=0, le=100000)
    accepts_veg: Optional[bool] = None
    accepts_non_veg: Optional[bool] = None
    pickup_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    pickup_end_hour: Optional[int] = Field(default=None, ge=0, le=24)
    has_vehicle: Optional[bool] = None


class NgoPublic(BaseModel):
    id: int
    organization_name: str
    area: str


class VolunteerOut(BaseModel):
    user_id: int
    full_name: str
    phone: Optional[str]
    vehicle_type: Optional[str]
    area: Optional[str]
    is_available: bool
    active_assignments: int


# ---------- Listings ----------
class ListingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    food_type: str = Field(min_length=2, max_length=200)
    food_category: FoodCategory
    portions_reported: int = Field(gt=0, le=100000)
    prepared_at: datetime
    pickup_deadline: datetime
    storage_condition: Optional[Storage] = None
    packaging: Optional[str] = Field(default=None, max_length=120)
    allergens: Optional[str] = Field(default=None, max_length=200)
    pickup_address: str = Field(min_length=5, max_length=300)
    area: str = Field(min_length=2, max_length=100)
    latitude: Lat
    longitude: Lng
    source: Literal["MANUAL", "VOICE"] = "MANUAL"
    voice_transcript: Optional[str] = Field(default=None, max_length=5000)
    voice_language: Optional[Language] = None
    predicted_surplus_portions: Optional[int] = Field(default=None, ge=0)
    voice_confirmed: bool = False

    @field_validator("prepared_at", "pickup_deadline")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return to_naive_utc(v)

    @model_validator(mode="after")
    def _check(self) -> "ListingCreate":
        if self.pickup_deadline <= self.prepared_at:
            raise ValueError("pickup_deadline must be after prepared_at")
        if self.source == "VOICE" and not self.voice_confirmed:
            raise ValueError("Voice-extracted details must be confirmed by the donor (voice_confirmed=true)")
        return self


class ListingUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    food_type: Optional[str] = Field(default=None, min_length=2, max_length=200)
    food_category: Optional[FoodCategory] = None
    portions_reported: Optional[int] = Field(default=None, gt=0, le=100000)
    prepared_at: Optional[datetime] = None
    pickup_deadline: Optional[datetime] = None
    storage_condition: Optional[Storage] = None
    packaging: Optional[str] = Field(default=None, max_length=120)
    allergens: Optional[str] = Field(default=None, max_length=200)
    pickup_address: Optional[str] = Field(default=None, min_length=5, max_length=300)
    area: Optional[str] = Field(default=None, min_length=2, max_length=100)
    latitude: Optional[Lat] = None
    longitude: Optional[Lng] = None

    @field_validator("prepared_at", "pickup_deadline")
    @classmethod
    def _utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v) if v else v


class SafetyCheckOut(ORM):
    id: int
    result: str
    issues: List[Dict[str, Any]]
    review_decision: Optional[str]
    review_notes: Optional[str]
    reviewed_at: Optional[UTCDateTime]
    created_at: UTCDateTime


class HistoryOut(BaseModel):
    id: int
    from_status: Optional[str]
    to_status: str
    actor_name: Optional[str]
    actor_role: Optional[str]
    note: Optional[str]
    created_at: UTCDateTime


class MatchOut(BaseModel):
    ngo_id: int
    ngo_name: str
    ngo_area: str
    rank: int
    score: float
    distance_km: float
    components: Dict[str, Any]
    explanation: str
    decision: Optional[str] = None


class AssignmentOut(BaseModel):
    id: int
    listing_id: int
    volunteer_id: int
    volunteer_name: str
    status: str
    collected_portions: Optional[int]
    has_proof: bool
    collection_notes: Optional[str]
    picked_up_at: Optional[UTCDateTime]
    delivered_at: Optional[UTCDateTime]
    created_at: UTCDateTime


class DeliveryOut(BaseModel):
    collected_portions: int
    delivered_portions: int
    delivery_location: Optional[str]
    notes: Optional[str]
    receipt_number: str
    ngo_acknowledged_at: Optional[UTCDateTime]
    created_at: UTCDateTime


class ListingOut(BaseModel):
    """A listing as seen by the requesting user. Contact/precise-location fields are
    null unless the viewer is authorised (donor, admin, accepted NGO, assigned volunteer)."""

    id: int
    title: str
    description: Optional[str]
    food_type: str
    food_category: str
    portions_reported: int
    prepared_at: UTCDateTime
    pickup_deadline: UTCDateTime
    storage_condition: Optional[str]
    packaging: Optional[str]
    allergens: Optional[str]
    area: str
    latitude: float
    longitude: float
    location_precision: Literal["exact", "approximate"]
    pickup_address: Optional[str]
    donor_name: Optional[str]
    donor_phone: Optional[str]
    donor_organization: Optional[str]
    has_image: bool
    source: str
    voice_transcript: Optional[str]
    voice_language: Optional[str]
    predicted_surplus_portions: Optional[int]
    status: str
    emergency: bool
    is_demo: bool
    accepted_ngo_id: Optional[int]
    accepted_ngo_name: Optional[str]
    published_at: Optional[UTCDateTime]
    accepted_at: Optional[UTCDateTime]
    created_at: UTCDateTime
    updated_at: UTCDateTime
    my_match: Optional[MatchOut] = None


class ListingDetail(ListingOut):
    history: List[HistoryOut]
    safety_checks: List[SafetyCheckOut]
    matches: List[MatchOut]
    assignment: Optional[AssignmentOut]
    delivery: Optional[DeliveryOut]
    safety_disclaimer: str
    viewer_can: Dict[str, bool]


class PublishResult(BaseModel):
    listing: ListingDetail
    safety_result: str
    issues: List[Dict[str, Any]]
    matches_found: int
    message: str


class DecisionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300)


class AssignRequest(BaseModel):
    volunteer_user_id: int


class DeliveryRequest(BaseModel):
    delivered_portions: int = Field(ge=0, le=100000)
    delivery_location: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = Field(default=None, max_length=1000)


class ReceiptOut(BaseModel):
    receipt_number: str
    listing_id: int
    donor_organization: str
    donor_name: str
    ngo_name: str
    volunteer_name: str
    food_type: str
    food_category: str
    portions_reported: int
    portions_collected: int
    portions_delivered: int
    prepared_at: UTCDateTime
    picked_up_at: Optional[UTCDateTime]
    delivered_at: UTCDateTime
    is_demo: bool
    statement: str


# ---------- Admin ----------
class VerifyNgoRequest(BaseModel):
    decision: Literal["VERIFIED", "REJECTED", "SUSPENDED"]
    notes: Optional[str] = Field(default=None, max_length=1000)


class SafetyReviewRequest(BaseModel):
    decision: Literal["CLEARED", "REJECTED"]
    notes: str = Field(min_length=3, max_length=1000)


class UserAdminUpdate(BaseModel):
    is_active: bool


class FlagOverrideRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = Field(default=None, max_length=300)


class NotificationOut(ORM):
    id: int
    listing_id: Optional[int]
    type: str
    channel: str
    language: str
    title: str
    body: str
    original_body: Optional[str]
    translation_source: Optional[str]
    status: str
    error: Optional[str]
    created_at: UTCDateTime
    read_at: Optional[UTCDateTime]


class IncidentOut(ORM):
    id: int
    category: str
    severity: str
    title: str
    details: Dict[str, Any]
    status: str
    occurrences: int
    first_seen: UTCDateTime
    last_seen: UTCDateTime
    resolved_at: Optional[UTCDateTime]


# ---------- AI ----------
class TextReportRequest(BaseModel):
    text: str = Field(min_length=5, max_length=3000)
    language: Language = "en"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    source: Language
    target: Language


class HistoricalEvent(BaseModel):
    planned_servings: int = Field(gt=0, le=100000)
    consumed_servings: int = Field(ge=0, le=100000)


class PredictRequest(BaseModel):
    event_type: Literal["WEDDING", "CORPORATE", "FESTIVAL", "RESTAURANT_DAY", "OTHER"] = "WEDDING"
    planned_servings: int = Field(gt=0, le=100000)
    expected_attendance: int = Field(gt=0, le=100000)
    actual_attendance: Optional[int] = Field(default=None, ge=0, le=100000)
    historical: List[HistoricalEvent] = Field(default_factory=list, max_length=50)
