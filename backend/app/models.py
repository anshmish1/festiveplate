"""SQLAlchemy ORM models for FestivePlate.

All timestamps are stored as naive UTC. Enumerations are stored as strings
guarded by CHECK constraints so that the schema is portable between PostgreSQL
(production) and SQLite (unit tests).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _in(col: str, values: List[str]) -> str:
    return f"{col} IN (" + ",".join(f"'{v}'" for v in values) + ")"


ROLES = ["DONOR", "NGO", "VOLUNTEER", "ADMIN"]
LANGUAGES = ["en", "kn", "hi"]
DONOR_TYPES = ["WEDDING_HALL", "RESTAURANT", "HOTEL", "CATERER", "EVENT_ORGANIZER", "HOUSEHOLD", "OTHER"]
NGO_VERIFICATION = ["PENDING", "VERIFIED", "REJECTED", "SUSPENDED"]
FOOD_CATEGORIES = ["VEG", "NON_VEG", "EGG", "MIXED"]
STORAGE_CONDITIONS = ["HOT_HELD", "REFRIGERATED", "ROOM_TEMPERATURE", "FROZEN"]
LISTING_STATUSES = [
    "DRAFT",
    "PUBLISHED",
    "MATCHED",
    "ACCEPTED",
    "PICKUP_ASSIGNED",
    "PICKED_UP",
    "DELIVERED",
    "CANCELLED",
    "EXPIRED",
    "FLAGGED",
]
LISTING_SOURCES = ["MANUAL", "VOICE"]
ASSIGNMENT_STATUSES = ["ASSIGNED", "PICKED_UP", "DELIVERED", "CANCELLED"]
NOTIFICATION_STATUSES = ["SENT", "FAILED", "READ"]
INCIDENT_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="ck_users_role"),
        CheckConstraint(_in("preferred_language", LANGUAGES), name="ck_users_language"),
        Index("ix_users_role", "role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    notify_in_app: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    donor_profile: Mapped[Optional["DonorProfile"]] = relationship(back_populates="user", uselist=False)
    ngo_profile: Mapped[Optional["NgoProfile"]] = relationship(
        back_populates="user", uselist=False, foreign_keys="NgoProfile.user_id"
    )
    volunteer_profile: Mapped[Optional["VolunteerProfile"]] = relationship(back_populates="user", uselist=False)


class DonorProfile(TimestampMixin, Base):
    __tablename__ = "donor_profiles"
    __table_args__ = (
        CheckConstraint(_in("donor_type", DONOR_TYPES), name="ck_donor_type"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_donor_coords"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    organization_name: Mapped[str] = mapped_column(String(160), nullable=False)
    donor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    user: Mapped[User] = relationship(back_populates="donor_profile")


class NgoProfile(TimestampMixin, Base):
    __tablename__ = "ngo_profiles"
    __table_args__ = (
        CheckConstraint(_in("verification_status", NGO_VERIFICATION), name="ck_ngo_verification"),
        CheckConstraint("service_radius_km > 0 AND service_radius_km <= 100", name="ck_ngo_radius"),
        CheckConstraint("daily_capacity_portions > 0", name="ck_ngo_capacity"),
        CheckConstraint("pickup_start_hour BETWEEN 0 AND 23 AND pickup_end_hour BETWEEN 0 AND 24", name="ck_ngo_hours"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_ngo_coords"),
        Index("ix_ngo_verification", "verification_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    organization_name: Mapped[str] = mapped_column(String(160), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(80), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    service_radius_km: Mapped[float] = mapped_column(Float, nullable=False, default=10)
    daily_capacity_portions: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    accepts_veg: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accepts_non_veg: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pickup_start_hour: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # IST, inclusive
    pickup_end_hour: Mapped[int] = mapped_column(Integer, default=24, nullable=False)  # IST, exclusive; may wrap
    has_vehicle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text)
    verified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="ngo_profile", foreign_keys=[user_id])
    volunteers: Mapped[List["VolunteerProfile"]] = relationship(back_populates="ngo")


class VolunteerProfile(TimestampMixin, Base):
    __tablename__ = "volunteer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("ngo_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    vehicle_type: Mapped[Optional[str]] = mapped_column(String(40))
    area: Mapped[Optional[str]] = mapped_column(String(100))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="volunteer_profile")
    ngo: Mapped[NgoProfile] = relationship(back_populates="volunteers")


class FoodListing(TimestampMixin, Base):
    __tablename__ = "food_listings"
    __table_args__ = (
        CheckConstraint(_in("status", LISTING_STATUSES), name="ck_listing_status"),
        CheckConstraint(_in("food_category", FOOD_CATEGORIES), name="ck_listing_category"),
        CheckConstraint(
            "storage_condition IS NULL OR " + _in("storage_condition", STORAGE_CONDITIONS), name="ck_listing_storage"
        ),
        CheckConstraint(_in("source", LISTING_SOURCES), name="ck_listing_source"),
        CheckConstraint("portions_reported > 0 AND portions_reported <= 100000", name="ck_listing_portions"),
        CheckConstraint("pickup_deadline > prepared_at", name="ck_listing_deadline_after_prep"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_listing_coords"),
        Index("ix_listing_status_deadline", "status", "pickup_deadline"),
        Index("ix_listing_donor", "donor_id"),
        Index("ix_listing_accepted_ngo", "accepted_ngo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    food_type: Mapped[str] = mapped_column(String(200), nullable=False)
    food_category: Mapped[str] = mapped_column(String(20), nullable=False)
    portions_reported: Mapped[int] = mapped_column(Integer, nullable=False)
    prepared_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    storage_condition: Mapped[Optional[str]] = mapped_column(String(30))
    packaging: Mapped[Optional[str]] = mapped_column(String(120))
    allergens: Mapped[Optional[str]] = mapped_column(String(200))
    pickup_address: Mapped[str] = mapped_column(String(300), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(10), default="MANUAL", nullable=False)
    voice_transcript: Mapped[Optional[str]] = mapped_column(Text)
    voice_language: Mapped[Optional[str]] = mapped_column(String(10))
    predicted_surplus_portions: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    accepted_ngo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ngo_profiles.id", ondelete="SET NULL"))
    emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    donor: Mapped[User] = relationship(foreign_keys=[donor_id])
    accepted_ngo: Mapped[Optional[NgoProfile]] = relationship(foreign_keys=[accepted_ngo_id])
    history: Mapped[List["DonationStatusHistory"]] = relationship(
        back_populates="listing", order_by="DonationStatusHistory.id"
    )
    safety_checks: Mapped[List["FoodSafetyCheck"]] = relationship(
        back_populates="listing", order_by="FoodSafetyCheck.id"
    )
    matches: Mapped[List["NgoMatch"]] = relationship(back_populates="listing", order_by="NgoMatch.rank")


class FoodSafetyCheck(Base):
    __tablename__ = "food_safety_checks"
    __table_args__ = (
        CheckConstraint(_in("result", ["ELIGIBLE", "FLAGGED"]), name="ck_safety_result"),
        CheckConstraint(
            "review_decision IS NULL OR " + _in("review_decision", ["CLEARED", "REJECTED"]),
            name="ck_safety_review_decision",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    issues: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    review_decision: Mapped[Optional[str]] = mapped_column(String(10))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    listing: Mapped[FoodListing] = relationship(back_populates="safety_checks")


class NgoMatch(Base):
    __tablename__ = "ngo_matches"
    __table_args__ = (
        UniqueConstraint("listing_id", "ngo_id", name="uq_match_listing_ngo"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_match_score"),
        Index("ix_match_ngo", "ngo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("ngo_profiles.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    listing: Mapped[FoodListing] = relationship(back_populates="matches")
    ngo: Mapped[NgoProfile] = relationship()


class DonationAcceptance(Base):
    __tablename__ = "donation_acceptances"
    __table_args__ = (
        CheckConstraint(_in("decision", ["ACCEPTED", "REJECTED"]), name="ck_acceptance_decision"),
        UniqueConstraint("listing_id", "ngo_id", name="uq_acceptance_listing_ngo"),
        # Second line of defence against double acceptance: only one ACCEPTED row per listing.
        Index(
            "uq_acceptance_one_accepted",
            "listing_id",
            unique=True,
            postgresql_where=text("decision = 'ACCEPTED'"),
            sqlite_where=text("decision = 'ACCEPTED'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), nullable=False)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("ngo_profiles.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    decided_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    ngo: Mapped[NgoProfile] = relationship()


class PickupAssignment(TimestampMixin, Base):
    __tablename__ = "pickup_assignments"
    __table_args__ = (
        CheckConstraint(_in("status", ASSIGNMENT_STATUSES), name="ck_assignment_status"),
        CheckConstraint("collected_portions IS NULL OR collected_portions >= 0", name="ck_assignment_collected"),
        Index(
            "uq_assignment_one_active",
            "listing_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
            sqlite_where=text("status <> 'CANCELLED'"),
        ),
        Index("ix_assignment_volunteer", "volunteer_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), nullable=False)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("ngo_profiles.id", ondelete="CASCADE"), nullable=False)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="ASSIGNED", nullable=False)
    collected_portions: Mapped[Optional[int]] = mapped_column(Integer)
    collection_proof_path: Mapped[Optional[str]] = mapped_column(String(300))
    collection_notes: Mapped[Optional[str]] = mapped_column(Text)
    picked_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    listing: Mapped[FoodListing] = relationship()
    volunteer: Mapped[User] = relationship(foreign_keys=[volunteer_id])
    ngo: Mapped[NgoProfile] = relationship()


class DonationStatusHistory(Base):
    __tablename__ = "donation_status_history"
    __table_args__ = (
        CheckConstraint("from_status IS NULL OR " + _in("from_status", LISTING_STATUSES), name="ck_history_from"),
        CheckConstraint(_in("to_status", LISTING_STATUSES), name="ck_history_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    listing: Mapped[FoodListing] = relationship(back_populates="history")
    actor: Mapped[Optional[User]] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(_in("status", NOTIFICATION_STATUSES), name="ck_notification_status"),
        CheckConstraint(_in("channel", ["IN_APP", "SMS_SIMULATED"]), name="ck_notification_channel"),
        Index("ix_notification_user", "user_id", "created_at"),
        Index("ix_notification_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    listing_id: Mapped[Optional[int]] = mapped_column(ForeignKey("food_listings.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(15), default="IN_APP", nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    original_body: Mapped[Optional[str]] = mapped_column(Text)
    translation_source: Mapped[Optional[str]] = mapped_column(String(20))  # sarvam | none | failed
    status: Mapped[str] = mapped_column(String(10), default="SENT", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class DeliveryConfirmation(Base):
    __tablename__ = "delivery_confirmations"
    __table_args__ = (
        CheckConstraint("delivered_portions >= 0", name="ck_delivery_portions"),
        CheckConstraint("collected_portions >= 0", name="ck_delivery_collected"),
        CheckConstraint("delivered_portions <= collected_portions", name="ck_delivery_le_collected"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("food_listings.id", ondelete="CASCADE"), unique=True, nullable=False)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("pickup_assignments.id", ondelete="CASCADE"), nullable=False)
    collected_portions: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered_portions: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_location: Mapped[Optional[str]] = mapped_column(String(300))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    confirmed_by_volunteer: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    ngo_acknowledged_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ngo_acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    receipt_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class FeatureFlagOverride(Base):
    __tablename__ = "feature_flag_overrides"

    flag_name: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class FeatureFlagAudit(Base):
    __tablename__ = "feature_flag_audit"
    __table_args__ = (Index("ix_flag_audit_name", "flag_name", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    flag_name: Mapped[str] = mapped_column(String(60), nullable=False)
    old_value: Mapped[Optional[bool]] = mapped_column(Boolean)
    new_value: Mapped[Optional[bool]] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # local_override | flagsmith | default
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ApplicationIncident(Base):
    __tablename__ = "application_incidents"
    __table_args__ = (
        CheckConstraint(_in("severity", INCIDENT_SEVERITIES), name="ck_incident_severity"),
        CheckConstraint(_in("status", ["OPEN", "RESOLVED"]), name="ck_incident_status"),
        Index("ix_incident_status", "status", "last_seen"),
        Index("ix_incident_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"), Index("ix_audit_created", "created_at"))

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    details: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
