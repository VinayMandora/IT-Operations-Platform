"""Manual Google Directory lab CLI: mock by default, no app integration."""
import argparse
import getpass
import os
from app.services.google_directory import MockDirectory, RealGoogleDirectory


def main():
    parser = argparse.ArgumentParser(description='Standalone Google Workspace lab (mock default)')
    parser.add_argument('--action', choices=['create','list','group','update','suspend'], default='list')
    parser.add_argument('--email', default='nc000001@northstar.example')
    parser.add_argument('--group', default='claims-team@northstar.example')
    parser.add_argument('--lab-live', action='store_true')
    parser.add_argument('--commit-lab-changes', action='store_true')
    args = parser.parse_args()
    if args.commit_lab_changes and not args.lab_live:
        parser.error('Cannot commit without --lab-live')
    if args.lab_live and args.action != 'list' and not args.commit_lab_changes:
        parser.error('Real write operations require --commit-lab-changes; default is mock')
    if args.commit_lab_changes:
        confirmation = input('Type WORKSPACE ISOLATED LAB to continue: ')
        if confirmation != 'WORKSPACE ISOLATED LAB':
            raise SystemExit('Cancelled without changes')
    directory = RealGoogleDirectory(confirmed_lab=True) if args.lab_live else MockDirectory()
    if not args.lab_live and args.action != 'create':
        directory.create_user(args.email, 'Alex', 'Morgan')
    if args.action == 'create':
        password = getpass.getpass('One-time lab-only user password: ') if args.lab_live else None
        result = directory.create_user(args.email, 'Alex', 'Morgan', password)
    elif args.action == 'list':
        result = directory.list_users()
    elif args.action == 'group':
        result = directory.assign_group(args.email, args.group)
    elif args.action == 'update':
        result = directory.update_user(args.email, {'orgUnitPath': '/LabUsers'})
    else:
        result = directory.suspend_user(args.email)
    # Never log password, token, or full credential objects.
    print(f'{"LIVE LAB" if args.lab_live else "MOCK"} {args.action}: completed')
    if isinstance(result, list):
        print('Users returned:', len(result))
    else:
        print('Target:', result.get('primaryEmail', args.email))


if __name__ == '__main__':
    main()
