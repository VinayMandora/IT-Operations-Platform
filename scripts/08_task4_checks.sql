USE ClaimsITOpsDemo;
GO
SELECT name FROM sys.tables WHERE name IN ('claims','tickets','employees','claim_crm_states',
 'workflow_rules','workflow_executions','workflow_transitions','crm_operations','communication_templates') ORDER BY name;
SELECT COUNT(*) AS claims_preserved FROM dbo.claims;
SELECT COUNT(*) AS support_tickets_preserved FROM dbo.tickets;
SELECT c.claim_id,c.claimant_name,c.status,s.stage,s.assigned_handler,s.integration_status,
 s.missing_documents,s.completed_at FROM dbo.claims c LEFT JOIN dbo.claim_crm_states s ON s.claim_id=c.id ORDER BY c.id;
SELECT e.id,r.name,c.claim_id,e.started_at,e.status,e.input_status,e.output_status,e.error_reason,
 e.retry_count,e.support_ticket_id FROM dbo.workflow_executions e
 JOIN dbo.workflow_rules r ON r.id=e.rule_id JOIN dbo.claims c ON c.id=e.claim_id ORDER BY e.id DESC;
SELECT operation_key,operation,status,retry_count,error_reason FROM dbo.crm_operations ORDER BY id DESC;
SELECT event_type,occurred_at FROM dbo.audit_events WHERE event_type LIKE 'CLAIM_%' ORDER BY id DESC;
SELECT claim_id,rule_id,event_key,COUNT(*) AS duplicates FROM dbo.workflow_executions
 GROUP BY claim_id,rule_id,event_key HAVING COUNT(*) > 1;
GO
