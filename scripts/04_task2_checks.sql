USE ClaimsITOpsDemo;
GO
SELECT COUNT(*) AS original_claims_intact FROM dbo.claims;
SELECT event_type, COUNT(*) AS events FROM dbo.audit_events GROUP BY event_type;
SELECT t.id, CONCAT('TKT-',RIGHT('000000' + CAST(t.id AS VARCHAR(12)),6)) AS reference,
       t.title, t.priority, t.status, t.sla_due_at,
       u.full_name AS employee, tech.full_name AS technician
FROM dbo.tickets t
JOIN dbo.users u ON u.id=t.employee_id
LEFT JOIN dbo.users tech ON tech.id=t.assigned_technician_id;
SELECT asset_tag, status, assigned_employee_id FROM dbo.assets ORDER BY asset_tag;
SELECT asset_id, employee_id, action, occurred_at FROM dbo.asset_movements ORDER BY id DESC;
SELECT ticket_id, action, previous_status, new_status, occurred_at
FROM dbo.ticket_history ORDER BY id DESC;
SELECT asset_tag, COUNT(*) AS duplicated FROM dbo.assets GROUP BY asset_tag HAVING COUNT(*)>1;
SELECT COUNT(*) AS overdue_tickets FROM dbo.tickets
 WHERE status NOT IN ('Resolved','Closed') AND sla_due_at < GETUTCDATE();
GO
