USE ClaimsITOpsDemo;
GO
SELECT name FROM sys.tables WHERE name IN
 ('claims','tickets','assets','audit_events','employees','onboarding_requests',
  'offboarding_requests','provisioning_actions','approval_records','asset_reservations') ORDER BY name;
SELECT id,full_name,department,status,work_email FROM dbo.employees ORDER BY id DESC;
SELECT id,employee_id,status,requested_groups_json,device_requirements_json FROM dbo.onboarding_requests ORDER BY id DESC;
SELECT id,employee_id,status,approved_by FROM dbo.offboarding_requests ORDER BY id DESC;
SELECT action_type,target,status,result_detail FROM dbo.provisioning_actions ORDER BY id DESC;
SELECT a.asset_tag,a.status,r.employee_id,r.status AS reservation_status FROM dbo.assets a
 LEFT JOIN dbo.asset_reservations r ON r.asset_id=a.id AND r.status='Reserved';
SELECT event_type,occurred_at,actor_user_id FROM dbo.audit_events ORDER BY id DESC;
SELECT asset_id,COUNT(*) AS active_reservations FROM dbo.asset_reservations WHERE status='Reserved'
 GROUP BY asset_id HAVING COUNT(*)>1;
SELECT COUNT(*) AS preserved_claims FROM dbo.claims;
SELECT COUNT(*) AS preserved_tickets FROM dbo.tickets;
GO
