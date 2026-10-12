USE ClaimsITOpsDemo;
GO
-- Task 1 checks and Task 2 incident relationship
SELECT 'Claims' AS component, COUNT(*) AS records FROM dbo.claims
UNION ALL SELECT 'Helpdesk tickets',COUNT(*) FROM dbo.tickets
UNION ALL SELECT 'Employees',COUNT(*) FROM dbo.employees
UNION ALL SELECT 'Claim CRM states',COUNT(*) FROM dbo.claim_crm_states
UNION ALL SELECT 'Network checks',COUNT(*) FROM dbo.network_checks
UNION ALL SELECT 'Device health',COUNT(*) FROM dbo.device_health_checks
UNION ALL SELECT 'Calls',COUNT(*) FROM dbo.call_logs
UNION ALL SELECT 'IVR rules',COUNT(*) FROM dbo.ivr_rules
UNION ALL SELECT 'Backups',COUNT(*) FROM dbo.backup_jobs
UNION ALL SELECT 'Monitoring events',COUNT(*) FROM dbo.monitoring_events;
GO
SELECT TOP (20) n.created_at,n.check_type,n.target,n.port,n.result,n.elapsed_ms,
       t.id AS incident_id,t.title AS incident_title
FROM dbo.network_checks n LEFT JOIN dbo.tickets t ON t.id=n.ticket_id
ORDER BY n.id DESC;
SELECT TOP (20) c.extension,c.direction,c.outcome,c.route,COUNT(*) AS call_count
FROM dbo.call_logs c GROUP BY c.extension,c.direction,c.outcome,c.route ORDER BY call_count DESC;
SELECT TOP (20) b.created_at,b.backup_type,b.result,b.location,b.verified_at,b.failure_reason,
       t.id AS incident_id
FROM dbo.backup_jobs b LEFT JOIN dbo.tickets t ON b.ticket_id=t.id ORDER BY b.id DESC;
SELECT TOP (20) event_type,severity,message,ticket_id,created_at
FROM dbo.monitoring_events ORDER BY id DESC;
SELECT TOP (25) event_type,actor_user_id,occurred_at FROM dbo.audit_events ORDER BY id DESC;
GO
