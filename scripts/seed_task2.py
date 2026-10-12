"""Idempotent fictional accounts, devices and tickets; localhost demo ONLY."""
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset, Ticket, User, utc_now
from app.security import hash_password
from app.services.helpdesk_service import ticket_history, log_event

# Change passwords before exposing any instance to others. Never real company accounts.
USERS = [
 ('admin', 'Alex Morgan', 'alex.morgan@northstar.example', 'Admin', 'NorthstarAdmin!2026'),
 ('tech.owen', 'Owen Hughes', 'owen.hughes@northstar.example', 'Technician', 'NorthstarTech!2026'),
 ('tech.maya', 'Maya Singh', 'maya.singh@northstar.example', 'Technician', 'NorthstarTech!2026'),
 ('employee.ellie', 'Ellie Carter', 'ellie.carter@northstar.example', 'Employee', 'NorthstarStaff!2026'),
 ('employee.jamie', 'Jamie Patel', 'jamie.patel@northstar.example', 'Employee', 'NorthstarStaff!2026'),
]

ASSETS = [
 ('NS-LAP-001','NS-DELL-1001','Laptop','Dell','Latitude 5440','Windows 11', 'Available'),
 ('NS-LAP-002','NS-LEN-1002','Laptop','Lenovo','ThinkPad T14','Windows 11', 'Available'),
 ('NS-DES-001','NS-HP-2001','Desktop','HP','ProDesk 400','Windows 11', 'Available'),
 ('NS-PRN-001','NS-BRO-3001','Printer','Brother','MFC-L8690CDW',None, 'Maintenance'),
 ('NS-RTR-001','NS-CIS-4001','Router','Cisco','ISR 1100',None, 'Available'),
 ('NS-SWT-001','NS-CIS-5001','Switch','Cisco','Catalyst 9200',None,'Available'),
]


def main():
    with Session(get_engine()) as db:
        for username, full_name, email, role, password in USERS:
            if not db.scalar(select(User).where(User.username == username)):
                db.add(User(username=username, full_name=full_name, email=email,
                            role=role, password_hash=hash_password(password), is_active=True))
        db.flush()
        users = {u.username: u for u in db.scalars(select(User))}
        for tag, serial, kind, manufacturer, model, os_name, state in ASSETS:
            if not db.scalar(select(Asset).where(Asset.asset_tag == tag)):
                db.add(Asset(asset_tag=tag, serial_number=serial, device_type=kind,
                             manufacturer=manufacturer, model=model, operating_system=os_name,
                             purchase_date=date(2025, 3, 10), warranty_expiry=date(2028, 3, 10),
                             status=state, notes='Fictional inventory demonstration'))
        db.flush()
        # Four realistic support examples; leave NS-LAP-001 free for the laptop demo.
        demo_tickets = [
            ('VPN disconnects during claims review', 'Remote VPN drops after login on the desktop workstation.',
             'Network', 'Medium', 'Open', 'employee.jamie', None, None),
            ('First-floor printer repeatedly jams', 'The Brother printer jams after feeding more than two pages.',
             'Printer', 'Medium', 'Assigned', 'employee.ellie', 'tech.owen', None),
            ('Repeated account lockouts', 'Microsoft account gets locked three times each morning.',
             'Account Access', 'High', 'In Progress', 'employee.jamie', 'tech.maya', None),
            ('Outlook add-in freezes on launch', 'The claims review add-in freezes Microsoft Outlook after startup.',
             'Software', 'Low', 'Resolved', 'employee.ellie', 'tech.owen',
             'Disabled faulty add-in, installed approved update and verified Outlook startup.'),
        ]
        for title, description, category, priority, status, owner, tech_name, resolution in demo_tickets:
            if db.scalar(select(Ticket).where(Ticket.title == title)):
                continue
            now = utc_now()
            tech = users[tech_name] if tech_name else None
            ticket = Ticket(employee_id=users[owner].id, title=title, description=description,
                            category=category, priority=priority, status=status,
                            assigned_technician_id=tech.id if tech else None,
                            assigned_at=now if tech else None,
                            resolved_at=now if status == 'Resolved' else None,
                            resolution_details=resolution,
                            created_at=now, sla_due_at=now + timedelta(hours={'Low':72,'Medium':24,'High':8,'Critical':2}[priority]))
            db.add(ticket)
            db.flush()
            ticket_history(db, ticket, users[owner], 'Created', new='Open')
            if tech:
                ticket_history(db, ticket, users['admin'], 'Assigned',
                               f'Assigned to {tech.full_name}', 'Open', 'Assigned')
                log_event(db, 'TICKET_ASSIGNED', users['admin'], ticket_id=ticket.id, technician_id=tech.id)
            if status == 'In Progress':
                ticket_history(db, ticket, tech, 'Status change', 'Investigating account policy and lockout logs', 'Assigned', 'In Progress')
                log_event(db, 'TICKET_UPDATED', tech, ticket_id=ticket.id, to_status='In Progress')
            if status == 'Resolved':
                ticket_history(db, ticket, tech, 'Status change', resolution, 'Assigned', 'Resolved')
                log_event(db, 'TICKET_UPDATED', tech, ticket_id=ticket.id, to_status='Resolved')
        db.commit()
    print('Fictional Task 2 users, six assets and four support tickets are ready (existing rows untouched).')
    for username, _, _, _, password in USERS:
        print(f'  {username:18} {password}')
    print('LOCAL DEMO ONLY: these credentials are not safe for production.')


if __name__ == '__main__':
    main()
