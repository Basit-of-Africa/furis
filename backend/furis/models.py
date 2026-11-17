"""FURIS database models (brief §12).

Design rules carried into the schema:
- Authorship (identity_matches / publication_authors) and institutional attribution
  (institutional_attributions) are stored separately and decided separately (§6.2).
- Canonical publications are separate from per-source records, which are never
  overwritten by another source (§10.3).
- UUID primary keys, JSONB for raw source metadata on PostgreSQL (§12.2).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(e: type[enum.Enum]) -> Enum:
    # VARCHAR + CHECK constraint: portable and easy to extend with migrations.
    return Enum(e, native_enum=False, length=48, values_callable=lambda x: [m.value for m in x])


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    RESEARCH_OFFICE = "research_office"
    FACULTY_ADMIN = "faculty_admin"
    RESEARCHER = "researcher"


class EmploymentStatus(str, enum.Enum):
    ACTIVE = "active"
    FORMER = "former"
    ON_LEAVE = "on_leave"


class IdentifierType(str, enum.Enum):
    ORCID = "orcid"
    OPENALEX = "openalex"
    SCOPUS = "scopus"
    WOS_RESEARCHER_ID = "wos_researcher_id"
    GOOGLE_SCHOLAR = "google_scholar"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OTHER = "other"


class VariantType(str, enum.Enum):
    SYSTEM_GENERATED = "system_generated"  # Category 1
    RESEARCHER_CONFIRMED = "researcher_confirmed"  # Category 2
    DISCOVERED = "discovered"  # Category 3


class ConfirmationStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class MatchConfidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REJECTED = "rejected"


class MatchStatus(str, enum.Enum):
    CANDIDATE = "candidate"  # awaiting review
    CONFIRMED = "confirmed"  # authorship confirmed by a human
    REJECTED = "rejected"  # human or evidence says different person


class AttributionStatus(str, enum.Enum):
    CONFIRMED_FU_OUTPUT = "confirmed_fu_output"
    RESEARCHER_PUBLICATION_NOT_FU = "researcher_publication_not_fu"
    UNDER_REVIEW = "under_review"
    POTENTIAL_FU_OUTPUT = "potential_fu_output"
    NOT_ATTRIBUTABLE = "not_attributable"


class VerificationType(str, enum.Enum):
    AUTHORSHIP = "authorship"
    ATTRIBUTION = "attribution"


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    TRUNCATED = "truncated"  # hit the per-query record cap
    FAILED = "failed"


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class DuplicateStatus(str, enum.Enum):
    PENDING = "pending"
    MERGED = "merged"
    DISTINCT = "distinct"


# ---------------------------------------------------------------------------
# Organisation and people
# ---------------------------------------------------------------------------


class Faculty(Base, TimestampMixin):
    __tablename__ = "faculties"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True)
    departments: Mapped[list[Department]] = relationship(back_populates="faculty")


class Department(Base, TimestampMixin):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("faculty_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    faculty_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("faculties.id"))
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(32))
    faculty: Mapped[Faculty] = relationship(back_populates="departments")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole))
    # Faculty admins are scoped to a faculty; researchers are linked to their record.
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("faculties.id"))
    researcher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("researchers.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Researcher(Base, TimestampMixin):
    __tablename__ = "researchers"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    staff_number: Mapped[str | None] = mapped_column(String(64), unique=True)
    first_name: Mapped[str] = mapped_column(String(128))
    middle_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str] = mapped_column(String(128), index=True)
    preferred_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("faculties.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        _enum(EmploymentStatus), default=EmploymentStatus.ACTIVE
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    identifiers: Mapped[list[ResearcherIdentifier]] = relationship(
        back_populates="researcher", cascade="all, delete-orphan"
    )
    name_variants: Mapped[list[NameVariant]] = relationship(
        back_populates="researcher", cascade="all, delete-orphan"
    )
    employment: Mapped[list[EmploymentHistory]] = relationship(
        back_populates="researcher", cascade="all, delete-orphan"
    )
    interests: Mapped[list[ResearcherInterest]] = relationship(
        back_populates="researcher", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


class ResearcherIdentifier(Base):
    __tablename__ = "researcher_identifiers"
    __table_args__ = (
        UniqueConstraint("identifier_type", "identifier_value"),
        Index("ix_researcher_identifiers_researcher", "researcher_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"))
    identifier_type: Mapped[IdentifierType] = mapped_column(_enum(IdentifierType))
    identifier_value: Mapped[str] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    researcher: Mapped[Researcher] = relationship(back_populates="identifiers")


class NameVariant(Base):
    __tablename__ = "name_variants"
    __table_args__ = (UniqueConstraint("researcher_id", "normalised_name"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"))
    variant_name: Mapped[str] = mapped_column(String(255))
    normalised_name: Mapped[str] = mapped_column(String(255), index=True)
    variant_type: Mapped[VariantType] = mapped_column(_enum(VariantType))
    confirmation_status: Mapped[ConfirmationStatus] = mapped_column(
        _enum(ConfirmationStatus), default=ConfirmationStatus.PENDING
    )
    source: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    researcher: Mapped[Researcher] = relationship(back_populates="name_variants")


class EmploymentHistory(Base, TimestampMixin):
    __tablename__ = "employment_history"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"), index=True)
    institution_name: Mapped[str] = mapped_column(String(255))
    is_fountain_university: Mapped[bool] = mapped_column(Boolean, default=True)
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("faculties.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # None = ongoing
    employment_type: Mapped[str | None] = mapped_column(String(64))  # full-time, joint, visiting…
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus), default=VerificationStatus.UNVERIFIED
    )
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    researcher: Mapped[Researcher] = relationship(back_populates="employment")


class ResearcherInterest(Base):
    __tablename__ = "researcher_interests"
    __table_args__ = (UniqueConstraint("researcher_id", "interest"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"))
    interest: Mapped[str] = mapped_column(String(255))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    researcher: Mapped[Researcher] = relationship(back_populates="interests")


# ---------------------------------------------------------------------------
# Publications
# ---------------------------------------------------------------------------


class Publication(Base, TimestampMixin):
    __tablename__ = "publications"
    __table_args__ = (Index("ix_publications_title_year", "normalised_title", "publication_year"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text)
    normalised_title: Mapped[str] = mapped_column(Text)
    # Stored normalised (lower-case, no resolver prefix). Unique prevents DOI duplicates.
    doi: Mapped[str | None] = mapped_column(String(255), unique=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date)
    document_type: Mapped[str | None] = mapped_column(String(64))
    journal_name: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    issn: Mapped[str | None] = mapped_column(String(64))
    landing_page_url: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    is_open_access: Mapped[bool | None] = mapped_column(Boolean)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list[PublicationSource]] = relationship(
        back_populates="publication", cascade="all, delete-orphan"
    )
    authors: Mapped[list[PublicationAuthor]] = relationship(
        back_populates="publication", cascade="all, delete-orphan", order_by="PublicationAuthor.author_position"
    )


class PublicationAuthor(Base):
    __tablename__ = "publication_authors"
    __table_args__ = (UniqueConstraint("publication_id", "author_position"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    # Set only once authorship is confirmed by a human.
    researcher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("researchers.id"), index=True)
    raw_author_name: Mapped[str] = mapped_column(String(512))
    author_position: Mapped[int] = mapped_column(Integer)
    orcid: Mapped[str | None] = mapped_column(String(32))
    source_author_id: Mapped[str | None] = mapped_column(String(255))
    identity_status: Mapped[MatchStatus | None] = mapped_column(_enum(MatchStatus))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    publication: Mapped[Publication] = relationship(back_populates="authors")


class PublicationSource(Base):
    __tablename__ = "publication_sources"
    __table_args__ = (UniqueConstraint("source_name", "source_record_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(32))
    source_record_id: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    citation_count: Mapped[int | None] = mapped_column(Integer)  # per-source, never merged (§15.2)
    raw_metadata: Mapped[dict] = mapped_column(JSONType)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    publication: Mapped[Publication] = relationship(back_populates="sources")


class PublicationAffiliation(Base):
    __tablename__ = "publication_affiliations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    researcher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("researchers.id"), index=True)
    author_position: Mapped[int | None] = mapped_column(Integer)
    raw_affiliation: Mapped[str] = mapped_column(Text)
    normalised_institution: Mapped[str | None] = mapped_column(String(512))
    institution_identifier: Mapped[str | None] = mapped_column(String(255))
    is_fountain_university: Mapped[bool] = mapped_column(Boolean, default=False)
    source_name: Mapped[str] = mapped_column(String(32))


class DuplicateCandidate(Base):
    """Uncertain duplicates (fuzzy title match) held for human review (§10.1)."""

    __tablename__ = "duplicate_candidates"
    __table_args__ = (UniqueConstraint("publication_id", "other_publication_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"))
    other_publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"))
    similarity: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[DuplicateStatus] = mapped_column(_enum(DuplicateStatus), default=DuplicateStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Matching, attribution and verification
# ---------------------------------------------------------------------------


class IdentityMatch(Base, TimestampMixin):
    __tablename__ = "identity_matches"
    __table_args__ = (UniqueConstraint("publication_id", "researcher_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"), index=True)
    author_position: Mapped[int | None] = mapped_column(Integer)
    matching_method: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[MatchConfidence] = mapped_column(_enum(MatchConfidence))
    confidence_score: Mapped[float] = mapped_column(Float)
    evidence_summary: Mapped[dict] = mapped_column(JSONType)
    match_status: Mapped[MatchStatus] = mapped_column(_enum(MatchStatus), default=MatchStatus.CANDIDATE)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstitutionalAttribution(Base, TimestampMixin):
    """Institutional attribution, decided independently of authorship (§6.2, §9)."""

    __tablename__ = "institutional_attributions"
    __table_args__ = (UniqueConstraint("publication_id", "researcher_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"), index=True)
    suggested_status: Mapped[AttributionStatus] = mapped_column(_enum(AttributionStatus))
    final_status: Mapped[AttributionStatus | None] = mapped_column(_enum(AttributionStatus))
    evidence: Mapped[dict] = mapped_column(JSONType)
    policy_version: Mapped[str] = mapped_column(String(32))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationRecord(Base):
    __tablename__ = "verification_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"), index=True)
    verification_type: Mapped[VerificationType] = mapped_column(_enum(VerificationType))
    decision: Mapped[str] = mapped_column(String(48))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    evidence: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiscoveryRequest(Base):
    """A queued discovery job. Used when the API runs on serverless hosting (Vercel),
    where a request cannot keep working after its response: a scheduled worker
    (`furis discover --pending`) picks these up."""

    __tablename__ = "discovery_requests"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"), index=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RequestStatus] = mapped_column(_enum(RequestStatus), default=RequestStatus.PENDING, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)


class SearchRun(Base):
    __tablename__ = "search_runs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)  # groups one discovery job
    researcher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("researchers.id"), index=True)
    source_name: Mapped[str] = mapped_column(String(32))
    search_query: Mapped[str] = mapped_column(Text)
    query_type: Mapped[str] = mapped_column(String(48))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    unique_records_found: Mapped[int] = mapped_column(Integer, default=0)
    candidates_matched: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    run_status: Mapped[RunStatus] = mapped_column(_enum(RunStatus), default=RunStatus.RUNNING)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    previous_value: Mapped[dict | None] = mapped_column(JSONType)
    new_value: Mapped[dict | None] = mapped_column(JSONType)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
