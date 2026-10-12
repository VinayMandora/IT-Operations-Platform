"""Existing Task 1 entities plus Task 2 IT helpdesk, users and asset inventory."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, text,
                        Integer, Numeric, String, UniqueConstraint, Unicode, UnicodeText)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("file_sha256", name="uq_import_batches_sha256"),
        CheckConstraint("total_rows >= 0 AND imported_rows >= 0 AND rejected_rows >= 0", name="ck_import_batches_nonnegative"),
        CheckConstraint("total_rows = imported_rows + rejected_rows", name="ck_import_batches_balance"),
        CheckConstraint("status IN ('Completed')", name="ck_import_batches_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Completed")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    claims: Mapped[list["Claim"]] = relationship(back_populates="batch")
    rejects: Mapped[list["RejectedRow"]] = relationship(back_populates="batch")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("claim_id", name="uq_claims_claim_id"),
        CheckConstraint("amount_gbp >= 0 AND amount_gbp <= 1000000", name="ck_claims_amount_range"),
        CheckConstraint("incident_date <= reported_date", name="ck_claims_date_order"),
        CheckConstraint("status IN ('Open','In Progress','Closed','Declined')", name="ck_claims_status"),
        CheckConstraint("claim_type IN ('Motor','Home','Travel','Business')", name="ck_claims_type"),
        Index("ix_claims_status", "status"), Index("ix_claims_reported_date", "reported_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(10), nullable=False)
    policy_number: Mapped[str] = mapped_column(String(10), nullable=False)
    claimant_name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(20), nullable=False)
    incident_date: Mapped[date] = mapped_column(Date, nullable=False)
    reported_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    postcode: Mapped[str] = mapped_column(String(8), nullable=False)
    description: Mapped[str] = mapped_column(Unicode(500), nullable=False, default="")
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    batch: Mapped[ImportBatch] = relationship(back_populates="claims")


class RejectedRow(Base):
    __tablename__ = "rejected_rows"
    __table_args__ = (CheckConstraint("source_row_number >= 2", name="ck_rejected_rows_source_row"),
                      Index("ix_rejected_rows_batch_id", "import_batch_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_reason: Mapped[str] = mapped_column(Unicode(1000), nullable=False)
    raw_data_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    batch: Mapped[ImportBatch] = relationship(back_populates="rejects")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("role IN ('Admin','Technician','Employee')", name="ck_users_role"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(60), nullable=False)
    full_name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("asset_tag", name="uq_assets_tag"),
        UniqueConstraint("serial_number", name="uq_assets_serial"),
        CheckConstraint("device_type IN ('Laptop','Desktop','Printer','Router','Switch')", name="ck_assets_type"),
        CheckConstraint("status IN ('Available','Assigned','Reserved','Maintenance','Retired')", name="ck_assets_status"),
        CheckConstraint("warranty_expiry IS NULL OR warranty_expiry >= purchase_date", name="ck_assets_warranty"),
        CheckConstraint("(status = 'Assigned' AND assigned_employee_id IS NOT NULL) OR (status <> 'Assigned' AND assigned_employee_id IS NULL)", name="ck_assets_assignment"),
        Index("ix_assets_status", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_tag: Mapped[str] = mapped_column(String(40), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False)
    manufacturer: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    model: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    operating_system: Mapped[str | None] = mapped_column(Unicode(100))
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    warranty_expiry: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Available")
    assigned_employee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str] = mapped_column(Unicode(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    assigned_employee: Mapped[User | None] = relationship(foreign_keys=[assigned_employee_id])


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("category IN ('Hardware','Software','Network','Printer','Account Access','Other')", name="ck_tickets_category"),
        CheckConstraint("priority IN ('Low','Medium','High','Critical')", name="ck_tickets_priority"),
        CheckConstraint("status IN ('Open','Assigned','In Progress','Resolved','Closed')", name="ck_tickets_status"),
        Index("ix_tickets_status_due", "status", "sla_due_at"),
        Index("ix_tickets_assignee", "assigned_technician_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    affected_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    title: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    description: Mapped[str] = mapped_column(Unicode(3000), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Open")
    resolution_details: Mapped[str | None] = mapped_column(Unicode(3000))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    sla_due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    technician: Mapped[User | None] = relationship(foreign_keys=[assigned_technician_id])
    asset: Mapped[Asset | None] = relationship()
    history: Mapped[list["TicketHistory"]] = relationship(back_populates="ticket", order_by="TicketHistory.id")

    @property
    def reference(self) -> str:
        # A reference backed by the SQL IDENTITY primary key cannot collide.
        return f"TKT-{self.id:06d}"


class TicketHistory(Base):
    __tablename__ = "ticket_history"
    __table_args__ = (Index("ix_ticket_history_ticket", "ticket_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Unicode(3000), nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    ticket: Mapped[Ticket] = relationship(back_populates="history")
    actor: Mapped[User] = relationship()


class AssetMovement(Base):
    __tablename__ = "asset_movements"
    __table_args__ = (Index("ix_asset_movements_asset", "asset_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(15), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    asset: Mapped[Asset] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('IMPORT_COMPLETED','TICKET_CREATED','TICKET_UPDATED','TICKET_ASSIGNED','TICKET_NOTE','ASSET_CREATED','ASSET_UPDATED','ASSET_ASSIGNED','ASSET_RETURNED','USER_CREATED','USER_UPDATED','EMPLOYEE_CREATED','EMPLOYEE_ACTIVATED','ONBOARDING_PREPARED','OFFBOARDING_REQUESTED','OFFBOARDING_APPROVED','OFFBOARDING_COMPLETED','ASSET_RESERVED','ASSET_RESERVATION_RELEASED','CLAIM_WORKFLOW','CLAIM_CRM_SYNC','CLAIM_TEMPLATE_UPDATED','CLAIM_WORKFLOW_FAILED','NETWORK_CHECK','DEVICE_HEALTH','CALLS_IMPORTED','IVR_UPDATED','BACKUP_CREATED','BACKUP_VERIFIED','BACKUP_FAILED')", name="ck_audit_events_type"),
        Index("ix_audit_events_batch_id", "import_batch_id"),
        Index("ix_audit_events_actor", "actor_user_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    details_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Employee(Base):
    """HR-facing record; separate from local helpdesk login accounts."""
    __tablename__ = 'employees'
    __table_args__ = (
        UniqueConstraint('work_email', name='uq_employees_work_email'),
        UniqueConstraint('ad_username', name='uq_employees_ad_username'),
        CheckConstraint("department IN ('Claims','Operations','Finance','HR','IT')", name='ck_employees_department'),
        CheckConstraint("status IN ('Prepared','Active','Offboarding','Offboarded')", name='ck_employees_status'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    department: Mapped[str] = mapped_column(String(30), nullable=False)
    job_title: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    manager_name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    work_email: Mapped[str] = mapped_column(String(180), nullable=False)
    ad_username: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='Prepared')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class OnboardingRequest(Base):
    __tablename__ = 'onboarding_requests'
    __table_args__ = (
        UniqueConstraint('employee_id', name='uq_onboarding_employee'),
        CheckConstraint("status IN ('Prepared','Attention','Activated')", name='ck_onboarding_status'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    requested_groups_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    device_requirements_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='Prepared')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    employee: Mapped[Employee] = relationship()


class OffboardingRequest(Base):
    __tablename__ = 'offboarding_requests'
    __table_args__ = (
        CheckConstraint("status IN ('PendingApproval','Approved','Completed','Attention')", name='ck_offboarding_status'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    last_working_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='PendingApproval')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    employee: Mapped[Employee] = relationship()


class ProvisioningAction(Base):
    __tablename__ = 'provisioning_actions'
    __table_args__ = (
        CheckConstraint("status IN ('Prepared','Mocked','Failed','ManualRequired')", name='ck_provisioning_status'),
        CheckConstraint('((onboarding_request_id IS NOT NULL AND offboarding_request_id IS NULL) OR (onboarding_request_id IS NULL AND offboarding_request_id IS NOT NULL))', name='ck_provisioning_one_request'),
        Index('ix_provisioning_employee', 'employee_id'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'), nullable=False)
    onboarding_request_id: Mapped[int | None] = mapped_column(ForeignKey('onboarding_requests.id'))
    offboarding_request_id: Mapped[int | None] = mapped_column(ForeignKey('offboarding_requests.id'))
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result_detail: Mapped[str] = mapped_column(Unicode(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class ApprovalRecord(Base):
    __tablename__ = 'approval_records'
    __table_args__ = (
        UniqueConstraint('offboarding_request_id', name='uq_approval_offboarding'),
        CheckConstraint("decision IN ('Approved','Rejected')", name='ck_approval_decision'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offboarding_request_id: Mapped[int] = mapped_column(ForeignKey('offboarding_requests.id'), nullable=False)
    approver_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class AssetReservation(Base):
    __tablename__ = 'asset_reservations'
    __table_args__ = (
        CheckConstraint("status IN ('Reserved','Released')", name='ck_reservation_status'),
        Index('uq_asset_active_reservation', 'asset_id', unique=True,
              sqlite_where=text("status = 'Reserved'"), mssql_where=text("status = 'Reserved'")),
        Index('uq_onboarding_active_reservation', 'onboarding_request_id', unique=True,
              sqlite_where=text("status = 'Reserved'"), mssql_where=text("status = 'Reserved'")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id'), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'), nullable=False)
    onboarding_request_id: Mapped[int] = mapped_column(ForeignKey('onboarding_requests.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='Reserved')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    asset: Mapped[Asset] = relationship()


# Task 4 is additive: Claim and all original status constraints remain unchanged.
class ClaimCRMState(Base):
    __tablename__ = 'claim_crm_states'
    __table_args__ = (
        UniqueConstraint('claim_id', name='uq_claim_crm_claim'),
        Index('uq_claim_crm_zoho', 'zoho_record_id', unique=True,
              sqlite_where=text('zoho_record_id IS NOT NULL'),
              mssql_where=text('zoho_record_id IS NOT NULL')),
        CheckConstraint("stage IN ('New','Assigned','Evidence Required','Ready for Review','Resolved')", name='ck_crm_stage'),
        CheckConstraint("integration_status IN ('Not Synced','Synced','Failed')", name='ck_crm_integration'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey('claims.id'), nullable=False)
    zoho_record_id: Mapped[str | None] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default='New')
    assigned_handler: Mapped[str | None] = mapped_column(Unicode(120))
    missing_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    integration_status: Mapped[str] = mapped_column(String(20), nullable=False, default='Not Synced')
    last_updated: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    claim: Mapped[Claim] = relationship()


class WorkflowRule(Base):
    __tablename__ = 'workflow_rules'
    __table_args__ = (
        UniqueConstraint('name', name='uq_workflow_rule_name'),
        CheckConstraint("event_type IN ('submitted','missing_documents','evidence_received','resolved')", name='ck_workflow_rule_event'),
        CheckConstraint("action_type IN ('assign_team','evidence_required','ready_for_review','resolve','demo_fail')", name='ck_workflow_rule_action'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parameters_json: Mapped[str] = mapped_column(UnicodeText, nullable=False, default='{}')
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class WorkflowExecution(Base):
    __tablename__ = 'workflow_executions'
    __table_args__ = (
        UniqueConstraint('claim_id', 'rule_id', 'event_key', name='uq_workflow_exact_event'),
        CheckConstraint("status IN ('Success','Failed')", name='ck_workflow_execution_status'),
        CheckConstraint('retry_count >= 0 AND retry_count <= 3', name='ck_workflow_retry_count'),
        Index('ix_workflow_status', 'status', 'started_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey('claims.id'), nullable=False)
    rule_id: Mapped[int] = mapped_column(ForeignKey('workflow_rules.id'), nullable=False)
    event_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    input_status: Mapped[str] = mapped_column(String(30), nullable=False)
    output_status: Mapped[str | None] = mapped_column(String(30))
    error_reason: Mapped[str | None] = mapped_column(Unicode(1000))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    support_ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'))
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    claim: Mapped[Claim] = relationship()
    rule: Mapped[WorkflowRule] = relationship()


class WorkflowTransition(Base):
    __tablename__ = 'workflow_transitions'
    __table_args__ = (UniqueConstraint('execution_id', name='uq_transition_execution'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey('workflow_executions.id'), nullable=False)
    claim_id: Mapped[int] = mapped_column(ForeignKey('claims.id'), nullable=False)
    from_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    to_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class CRMOperation(Base):
    __tablename__ = 'crm_operations'
    __table_args__ = (
        UniqueConstraint('operation_key', name='uq_crm_operation_key'),
        CheckConstraint("status IN ('Success','Failed')", name='ck_crm_operation_status'),
        CheckConstraint('retry_count >= 0 AND retry_count <= 3', name='ck_crm_operation_retry'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(100), nullable=False)
    claim_id: Mapped[int] = mapped_column(ForeignKey('claims.id'), nullable=False)
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_reason: Mapped[str | None] = mapped_column(Unicode(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class CommunicationTemplate(Base):
    __tablename__ = 'communication_templates'
    __table_args__ = (UniqueConstraint('kind', name='uq_communication_kind'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    body: Mapped[str] = mapped_column(Unicode(4000), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))


# Task 5: all rows are additive to the original Tasks 1–4 database.
class NetworkCheck(Base):
    __tablename__ = 'network_checks'
    __table_args__ = (
        CheckConstraint("check_type IN ('IPConfig','DNS','TCP')", name='ck_network_type'),
        CheckConstraint("result IN ('Pass','Fail','Unavailable')", name='ck_network_result'),
        CheckConstraint('elapsed_ms IS NULL OR elapsed_ms >= 0', name='ck_network_elapsed'),
        Index('ix_network_created', 'created_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(160), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    elapsed_ms: Mapped[Decimal | None] = mapped_column(Numeric(12,2))
    details_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class DeviceHealthCheck(Base):
    __tablename__ = 'device_health_checks'
    __table_args__ = (
        CheckConstraint("status IN ('Healthy','Warning','Unavailable')", name='ck_health_status'),
        CheckConstraint('definitions_age_days IS NULL OR definitions_age_days >= 0', name='ck_health_age'),
        CheckConstraint('disk_total_bytes IS NULL OR disk_total_bytes >= 0', name='ck_health_disk_total'),
        CheckConstraint('disk_free_bytes IS NULL OR disk_free_bytes >= 0', name='ck_health_disk_free'),
        Index('ix_health_created', 'created_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hostname: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    os_description: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    antivirus_status: Mapped[str] = mapped_column(String(40), nullable=False)
    realtime_protection: Mapped[str] = mapped_column(String(40), nullable=False)
    definitions_age_days: Mapped[int | None] = mapped_column(Integer)
    disk_total_bytes: Mapped[int | None] = mapped_column(Numeric(20,0))
    disk_free_bytes: Mapped[int | None] = mapped_column(Numeric(20,0))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    details_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class CallLog(Base):
    __tablename__ = 'call_logs'
    __table_args__ = (
        UniqueConstraint('call_reference', name='uq_call_reference'),
        CheckConstraint("direction IN ('Inbound','Outbound')", name='ck_call_direction'),
        CheckConstraint("outcome IN ('Answered','Missed','Voicemail')", name='ck_call_outcome'),
        CheckConstraint('duration_seconds >= 0 AND duration_seconds <= 86400', name='ck_call_duration'),
        Index('ix_call_occurred', 'occurred_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_reference: Mapped[str] = mapped_column(String(50), nullable=False)
    extension: Mapped[str] = mapped_column(String(12), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    route: Mapped[str] = mapped_column(String(120), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class IVRRule(Base):
    __tablename__ = 'ivr_rules'
    __table_args__ = (
        UniqueConstraint('menu_name', 'digit', name='uq_ivr_menu_digit'),
        CheckConstraint("destination_type IN ('Extension','Queue','Voicemail')", name='ck_ivr_destination'),
        CheckConstraint("digit IN ('0','1','2','3','4','5','6','7','8','9')", name='ck_ivr_digit'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_name: Mapped[str] = mapped_column(String(60), nullable=False)
    digit: Mapped[str] = mapped_column(String(1), nullable=False)
    label: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(20), nullable=False)
    destination: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))


class BackupJob(Base):
    __tablename__ = 'backup_jobs'
    __table_args__ = (
        CheckConstraint("backup_type IN ('ApplicationExport','SQLFull','Simulation')", name='ck_backup_type'),
        CheckConstraint("result IN ('Success','Failed')", name='ck_backup_result'),
        Index('ix_backup_created', 'created_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backup_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[str] = mapped_column(String(15), nullable=False)
    location: Mapped[str] = mapped_column(Unicode(300), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Numeric(20,0))
    sha256: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_reason: Mapped[str | None] = mapped_column(Unicode(1000))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class MonitoringEvent(Base):
    __tablename__ = 'monitoring_events'
    __table_args__ = (
        CheckConstraint("severity IN ('Info','Warning','Critical')", name='ck_monitoring_severity'),
        Index('ix_monitoring_created', 'created_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(15), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Unicode(1000), nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
