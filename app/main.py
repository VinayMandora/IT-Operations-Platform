"""Northstar Claims Ltd: Task 1 claims + Task 2 IT helpdesk and assets."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routers import (claim_report, claims_crm, claim_workflows, claim_pages, assets, auth, claims, dashboard, imports, it_reports,
                         pages, reports, tickets, employees, employee_pages, operations, operations_pages)

app = FastAPI(title='Northstar Claims — IT Operations Platform',
              description='Task 1 claims intake + Task 2 helpdesk and asset inventory',
              version='0.5.0')
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')
app.include_router(dashboard.router)
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(auth.users_router)
app.include_router(tickets.router)
app.include_router(assets.router)
app.include_router(claims.router)
app.include_router(imports.router)
app.include_router(reports.router)
app.include_router(it_reports.router)
app.include_router(employees.router)
app.include_router(employee_pages.router)
app.include_router(claims_crm.router)
app.include_router(claim_workflows.router)
app.include_router(claim_pages.router)
app.include_router(claim_report.router)
app.include_router(operations.router)
app.include_router(operations_pages.router)


@app.get('/health', tags=['operations'])
def health():
    return {'status': 'ok', 'service': 'northstar-claims-task5'}
