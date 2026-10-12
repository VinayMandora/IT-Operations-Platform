"""Zoho CRM V8 client interface, persistent demonstration mock and opt-in OAuth client.

Never log tokens or server response bodies; never send requests in mock mode.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import ROOT_DIR

REGIONS = {
    'US': ('https://accounts.zoho.com', 'https://www.zohoapis.com'),
    'EU': ('https://accounts.zoho.eu', 'https://www.zohoapis.eu'),
    'IN': ('https://accounts.zoho.in', 'https://www.zohoapis.in'),
    'AU': ('https://accounts.zoho.com.au', 'https://www.zohoapis.com.au'),
    'JP': ('https://accounts.zoho.jp', 'https://www.zohoapis.jp'),
    'CA': ('https://accounts.zohocloud.ca', 'https://www.zohoapis.ca'),
    'CN': ('https://accounts.zoho.com.cn', 'https://www.zohoapis.com.cn'),
}


class CRMError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        self.retryable = retryable
        super().__init__(message)


def _identifier(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,59}', value):
        raise ValueError('CRM module/field API names must be valid identifiers')
    return value


class MockZohoClient:
    """In-memory deterministic records, no credentials. Seeded once per process."""
    def __init__(self, records=None):
        path = ROOT_DIR / 'sample_data' / 'task4_zoho_mock.json'
        self.records = {str(r['id']): dict(r) for r in (records if records is not None
                        else json.loads(path.read_text(encoding='utf-8')))}

    def list_claims(self):
        return [dict(v) for v in self.records.values()]

    def get_claim(self, record_id: str):
        if record_id not in self.records:
            raise CRMError('CRM record not found')
        return dict(self.records[record_id])

    def update_status(self, record_id: str, status: str):
        if record_id not in self.records:
            raise CRMError('CRM record not found')
        self.records[record_id]['Status'] = status
        return dict(self.records[record_id])


class RealZohoClient:
    """Strict opt-in; application must explicitly select real mode using ZOHO_MODE=real."""
    def __init__(self, http_client=None):
        if os.getenv('ZOHO_MODE', 'mock').lower() != 'real' or os.getenv('ZOHO_REAL_ENABLED') != 'YES':
            raise RuntimeError('Real Zoho integration is disabled')
        region = os.getenv('ZOHO_REGION', 'EU').upper()
        if region not in REGIONS:
            raise ValueError('Unsupported Zoho region')
        self.accounts_url, expected_api = REGIONS[region]
        self.api_base = os.getenv('ZOHO_API_BASE_URL', expected_api).rstrip('/')
        parsed = urlparse(self.api_base)
        if parsed.scheme != 'https' or self.api_base != expected_api:
            raise ValueError('Zoho API base URL must match the selected region HTTPS endpoint')
        self.module = _identifier(os.getenv('ZOHO_MODULE', 'Claims'))
        self.status_field = _identifier(os.getenv('ZOHO_FIELD_STATUS', 'Status'))
        self.fields = {key: _identifier(os.getenv(env, default)) for key, env, default in [
            ('reference','ZOHO_FIELD_REFERENCE','Claim_Reference'),
            ('claimant','ZOHO_FIELD_CLAIMANT','Claimant_Name'),
            ('type','ZOHO_FIELD_TYPE','Claim_Type'),
            ('submitted','ZOHO_FIELD_SUBMITTED','Submission_Date'),
            ('missing','ZOHO_FIELD_MISSING','Missing_Documents'),
        ]}
        self.client_id = os.getenv('ZOHO_CLIENT_ID', '')
        self.client_secret = os.getenv('ZOHO_CLIENT_SECRET', '')
        self.refresh_token = os.getenv('ZOHO_REFRESH_TOKEN', '')
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise RuntimeError('Zoho OAuth values are not configured')
        self.http = http_client or httpx.Client(timeout=15, follow_redirects=False)
        self._access_token = None

    def _refresh(self):
        try:
            response = self.http.post(self.accounts_url + '/oauth/v2/token', data={
                'refresh_token': self.refresh_token, 'client_id': self.client_id,
                'client_secret': self.client_secret, 'grant_type': 'refresh_token'})
            if response.status_code != 200:
                raise CRMError('OAuth refresh failed', response.status_code in (429, 500, 502, 503, 504))
            token = response.json().get('access_token')
            if not token:
                raise CRMError('OAuth response has no access token')
            self._access_token = token
        except httpx.RequestError:
            raise CRMError('OAuth network error', True) from None

    def _call(self, method, suffix, **kwargs):
        if not self._access_token:
            self._refresh()
        for attempt in range(2):
            try:
                response = self.http.request(method, f'{self.api_base}/crm/v8/{self.module}{suffix}',
                    headers={'Authorization': f'Zoho-oauthtoken {self._access_token}'}, **kwargs)
            except httpx.RequestError:
                raise CRMError('Zoho network error', True) from None
            if response.status_code == 401 and attempt == 0:
                self._refresh()
                continue
            if response.status_code >= 400:
                raise CRMError(f'Zoho returned HTTP {response.status_code}',
                               response.status_code in (429, 500, 502, 503, 504))
            try:
                data = response.json()
            except ValueError:
                raise CRMError('Invalid Zoho JSON response', True) from None
            if method == 'PUT':
                item = data.get('data', [{}])[0]
                if item.get('code') != 'SUCCESS':
                    raise CRMError('Zoho declined the record update')
            return data
        raise CRMError('Zoho authorization failed')

    def _normalise(self, item):
        return {'id': str(item.get('id', '')),
                'Claim_Reference': item.get(self.fields['reference']),
                'Claimant_Name': item.get(self.fields['claimant']),
                'Claim_Type': item.get(self.fields['type']),
                'Submission_Date': item.get(self.fields['submitted']),
                'Missing_Documents': item.get(self.fields['missing']),
                'Status': item.get(self.status_field)}

    def list_claims(self):
        # Limited pagination is explicit (max 2,000). Schedule subsequent pulls for larger estates.
        items = []
        for page in range(1, 11):
            result = self._call('GET', '', params={'per_page': 200, 'page': page})
            items.extend(self._normalise(item) for item in result.get('data', []))
            if not result.get('info', {}).get('more_records', False):
                break
        return items

    def get_claim(self, record_id):
        if not re.fullmatch(r'[0-9]{1,30}', str(record_id)):
            raise CRMError('Invalid Zoho record ID')
        data = self._call('GET', '/' + str(record_id)).get('data', [])
        if not data:
            raise CRMError('CRM record not found')
        return self._normalise(data[0])

    def update_status(self, record_id, status):
        if not re.fullmatch(r'[0-9]{1,30}', str(record_id)):
            raise CRMError('Invalid Zoho record ID')
        self._call('PUT', '/' + str(record_id), json={'data': [{self.status_field: status}]})
        return self.get_claim(record_id)


def make_client():
    return RealZohoClient() if os.getenv('ZOHO_MODE', 'mock').lower() == 'real' else _mock_singleton()


_cached_mock = None


def _mock_singleton():
    global _cached_mock
    if _cached_mock is None:
        _cached_mock = MockZohoClient()
    return _cached_mock
