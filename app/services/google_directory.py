"""Google Workspace Directory adapters. Application always uses MockDirectory."""
import os
from dataclasses import dataclass, field

SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user',
    'https://www.googleapis.com/auth/admin.directory.group.member',
]


@dataclass
class MockDirectory:
    users: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)

    def create_user(self, email, given_name, family_name, password=None):
        if email in self.users:
            raise ValueError('Mock Google user already exists')
        entry = {'primaryEmail': email, 'name': {'givenName': given_name, 'familyName': family_name}, 'suspended': False}
        self.users[email] = entry
        return entry.copy()

    def list_users(self):
        return list(self.users.values())

    def assign_group(self, email, group):
        if email not in self.users:
            raise ValueError('Mock Google user does not exist')
        self.groups.setdefault(group, set()).add(email)
        return {'group': group, 'email': email, 'role': 'MEMBER'}

    def update_user(self, email, changes):
        if email not in self.users:
            raise ValueError('Mock Google user does not exist')
        allowed = {'orgUnitPath', 'suspended'}
        if not set(changes).issubset(allowed):
            raise ValueError('Unsupported mock update fields')
        self.users[email].update(changes)
        return self.users[email].copy()

    def suspend_user(self, email):
        return self.update_user(email, {'suspended': True})


class RealGoogleDirectory:
    """Separate opt-in lab adapter, NEVER instantiated by application routes."""
    def __init__(self, *, confirmed_lab=False):
        if not confirmed_lab or os.getenv('GOOGLE_LAB_ENABLED') != 'YES':
            raise RuntimeError('Live Google integration disabled; explicit lab opt-in required')
        service_account_file = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE', '')
        delegated_admin = os.environ.get('GOOGLE_DELEGATED_ADMIN', '')
        allowed_domain = os.environ.get('GOOGLE_LAB_DOMAIN', '')
        if not service_account_file or not delegated_admin or not allowed_domain:
            raise RuntimeError('Missing lab credential path, delegated admin, or allowed domain')
        self.domain = allowed_domain.lower()
        # google-api-python-client and google-auth are OPTIONAL lab dependencies.
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES).with_subject(delegated_admin)
        self.service = build('admin', 'directory_v1', credentials=credentials, cache_discovery=False)

    def _email(self, email):
        if not email.lower().endswith('@' + self.domain):
            raise ValueError('Outside explicitly allowed lab domain')
        return email

    def create_user(self, email, given_name, family_name, password=None):
        if not password or len(password) < 16:
            raise ValueError('A temporary password of at least 16 characters is required')
        return self.service.users().insert(body={
            'primaryEmail': self._email(email),
            'name': {'givenName': given_name, 'familyName': family_name},
            'password': password, 'changePasswordAtNextLogin': True,
        }).execute()

    def list_users(self):
        result, page = [], None
        while True:
            response = self.service.users().list(domain=self.domain, maxResults=100,
                                                  pageToken=page).execute()
            result.extend(response.get('users', []))
            page = response.get('nextPageToken')
            if not page:
                return result

    def assign_group(self, email, group):
        self._email(email)
        self._email(group)
        return self.service.members().insert(groupKey=group, body={'email': email, 'role': 'MEMBER'}).execute()

    def update_user(self, email, changes):
        if not set(changes).issubset({'orgUnitPath', 'suspended'}):
            raise ValueError('Unsupported user update')
        return self.service.users().patch(userKey=self._email(email), body=changes).execute()

    def suspend_user(self, email):
        return self.update_user(email, {'suspended': True})
