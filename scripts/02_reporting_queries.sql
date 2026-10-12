-- Run only AFTER: python -m scripts.init_schema and your first import.
USE ClaimsITOpsDemo;
GO
-- 1. Confirm row count and overall claim value.
SELECT COUNT(*) AS total_claims,
       COALESCE(SUM(amount_gbp), 0) AS total_amount_gbp
FROM dbo.claims;
GO
-- 2. Claim totals by status.
SELECT status,
       COUNT(*) AS claim_count,
       SUM(amount_gbp) AS amount_gbp
FROM dbo.claims
GROUP BY status
ORDER BY status;
GO
-- 3. Unique claim ID check: expected zero results.
SELECT claim_id, COUNT(*) AS occurrences
FROM dbo.claims
GROUP BY claim_id
HAVING COUNT(*) > 1;
GO
-- 4. Rejected rows and failure reasons by batch.
SELECT r.import_batch_id, r.source_row_number, r.claim_id, r.failure_reason
FROM dbo.rejected_rows AS r
ORDER BY r.import_batch_id DESC, r.source_row_number;
GO
-- 5. Import outcomes (including rejected row counts).
SELECT id, filename, status, total_rows, imported_rows, rejected_rows, created_at
FROM dbo.import_batches
ORDER BY id DESC;
GO
-- 6. Monthly claim volumes (SQL Server syntax).
SELECT YEAR(reported_date) AS report_year,
       MONTH(reported_date) AS report_month,
       COUNT(*) AS claim_count
FROM dbo.claims
GROUP BY YEAR(reported_date), MONTH(reported_date)
ORDER BY report_year, report_month;
GO
-- 7. Auditable operations with source batch filename.
SELECT a.occurred_at, a.event_type, b.filename, a.details_json
FROM dbo.audit_events AS a
INNER JOIN dbo.import_batches AS b ON b.id = a.import_batch_id
ORDER BY a.occurred_at DESC;
GO
-- 8. Verify SQL Server check/unique/foreign key constraints exist.
SELECT 'CHECK' AS constraint_kind, name FROM sys.check_constraints
WHERE parent_object_id IN (OBJECT_ID('dbo.claims'), OBJECT_ID('dbo.import_batches'), OBJECT_ID('dbo.rejected_rows'), OBJECT_ID('dbo.audit_events'))
UNION ALL
SELECT 'UNIQUE', name FROM sys.key_constraints
WHERE type = 'UQ' AND parent_object_id IN (OBJECT_ID('dbo.claims'), OBJECT_ID('dbo.import_batches'))
UNION ALL
SELECT 'FOREIGN KEY', name FROM sys.foreign_keys
WHERE parent_object_id IN (OBJECT_ID('dbo.claims'), OBJECT_ID('dbo.rejected_rows'), OBJECT_ID('dbo.audit_events'));
GO
