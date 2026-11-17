from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from furis.discovery.text import normalise_orcid
from furis.models import (
    AttributionStatus,
    ConfirmationStatus,
    DuplicateStatus,
    EmploymentStatus,
    IdentifierType,
    MatchConfidence,
    MatchStatus,
    RunStatus,
    VariantType,
    VerificationStatus,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FacultyIn(BaseModel):
    name: str
    code: str | None = None


class FacultyOut(ORM, FacultyIn):
    id: uuid.UUID


class DepartmentIn(BaseModel):
    faculty_id: uuid.UUID
    name: str
    code: str | None = None


class DepartmentOut(ORM, DepartmentIn):
    id: uuid.UUID


class ResearcherIn(BaseModel):
    staff_number: str | None = None
    first_name: str = Field(min_length=1)
    middle_name: str | None = None
    last_name: str = Field(min_length=1)
    preferred_name: str | None = None
    email: str | None = None
    faculty_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE


class ResearcherPatch(BaseModel):
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    preferred_name: str | None = None
    email: str | None = None
    faculty_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    employment_status: EmploymentStatus | None = None


class IdentifierIn(BaseModel):
    identifier_type: IdentifierType
    identifier_value: str
    verified: bool = False

    @field_validator("identifier_value")
    @classmethod
    def _clean(cls, v: str, info):
        v = v.strip()
        if info.data.get("identifier_type") == IdentifierType.ORCID:
            o = normalise_orcid(v)
            if not o:
                raise ValueError("invalid ORCID")
            return o
        if info.data.get("identifier_type") == IdentifierType.OPENALEX:
            v = v.rsplit("/", 1)[-1].upper()
            if not v.startswith("A"):
                raise ValueError("OpenAlex author IDs start with 'A'")
        return v


class IdentifierOut(ORM):
    id: uuid.UUID
    identifier_type: IdentifierType
    identifier_value: str
    verified: bool
    verified_at: datetime | None


class VariantIn(BaseModel):
    variant_name: str = Field(min_length=2, max_length=255)


class VariantPatch(BaseModel):
    confirmation_status: ConfirmationStatus


class VariantOut(ORM):
    id: uuid.UUID
    variant_name: str
    variant_type: VariantType
    confirmation_status: ConfirmationStatus
    source: str | None


class EmploymentIn(BaseModel):
    institution_name: str
    is_fountain_university: bool = True
    faculty_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    employment_type: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    evidence_reference: str | None = None


class EmploymentOut(ORM, EmploymentIn):
    id: uuid.UUID


class ResearcherOut(ORM):
    id: uuid.UUID
    staff_number: str | None
    first_name: str
    middle_name: str | None
    last_name: str
    preferred_name: str | None
    email: str | None
    faculty_id: uuid.UUID | None
    department_id: uuid.UUID | None
    employment_status: EmploymentStatus


class ResearcherDetail(ResearcherOut):
    identifiers: list[IdentifierOut]
    name_variants: list[VariantOut]
    employment: list[EmploymentOut]


class SearchRunOut(ORM):
    id: uuid.UUID
    batch_id: uuid.UUID
    source_name: str
    search_query: str
    query_type: str
    started_at: datetime
    completed_at: datetime | None
    records_found: int
    records_processed: int
    unique_records_found: int
    candidates_matched: int
    error_message: str | None
    run_status: RunStatus


class PublicationOut(ORM):
    id: uuid.UUID
    title: str
    doi: str | None
    publication_year: int | None
    publication_date: date | None
    document_type: str | None
    journal_name: str | None
    publisher: str | None
    landing_page_url: str | None
    is_open_access: bool | None


class SourceOut(ORM):
    source_name: str
    source_record_id: str
    source_url: str | None
    citation_count: int | None
    retrieved_at: datetime


class AuthorOut(ORM):
    author_position: int
    raw_author_name: str
    orcid: str | None
    researcher_id: uuid.UUID | None
    identity_status: MatchStatus | None


class MatchOut(ORM):
    id: uuid.UUID
    publication_id: uuid.UUID
    researcher_id: uuid.UUID
    author_position: int | None
    matching_method: str
    confidence: MatchConfidence
    confidence_score: float
    evidence_summary: dict
    match_status: MatchStatus
    reviewed_at: datetime | None


class AttributionOut(ORM):
    id: uuid.UUID
    publication_id: uuid.UUID
    researcher_id: uuid.UUID
    suggested_status: AttributionStatus
    final_status: AttributionStatus | None
    evidence: dict
    policy_version: str
    decided_at: datetime | None


class PublicationDetail(PublicationOut):
    sources: list[SourceOut]
    authors: list[AuthorOut]
    matches: list[MatchOut] = []
    attributions: list[AttributionOut] = []
    affiliations: list[AffiliationOut] = []
    researchers: list[ResearcherRef] = []


class ResearcherRef(ORM):
    id: uuid.UUID
    first_name: str
    middle_name: str | None
    last_name: str
    staff_number: str | None


class QueueItem(BaseModel):
    match: MatchOut
    publication: PublicationOut
    attribution: AttributionOut | None
    researcher: ResearcherRef | None = None


class AffiliationOut(ORM):
    researcher_id: uuid.UUID | None
    author_position: int | None
    raw_affiliation: str
    normalised_institution: str | None
    is_fountain_university: bool
    source_name: str


class Me(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    faculty_id: uuid.UUID | None
    researcher_id: uuid.UUID | None
    must_change_password: bool = False


class AuthorshipDecision(BaseModel):
    publication_id: uuid.UUID
    researcher_id: uuid.UUID
    decision: MatchStatus  # confirmed | rejected
    evidence: str | None = None
    comments: str | None = None


class AttributionDecision(BaseModel):
    publication_id: uuid.UUID
    researcher_id: uuid.UUID
    status: AttributionStatus
    evidence: str | None = None
    comments: str | None = None


class DuplicateOut(ORM):
    id: uuid.UUID
    publication_id: uuid.UUID
    other_publication_id: uuid.UUID
    similarity: float
    reason: str
    status: DuplicateStatus
    publication: PublicationOut | None = None
    other_publication: PublicationOut | None = None


class DuplicateDecision(BaseModel):
    status: DuplicateStatus  # merged | distinct
