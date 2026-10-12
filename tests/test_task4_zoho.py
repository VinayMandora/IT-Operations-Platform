"""OAuth V8 wire behaviour tested locally with HTTP mock transport only."""
import logging
import httpx
import pytest
from app.services.zoho_client import RealZohoClient, CRMError, MockZohoClient


def settings(monkeypatch):
    for key, value in {
        'ZOHO_MODE':'real', 'ZOHO_REAL_ENABLED':'YES', 'ZOHO_REGION':'EU',
        'ZOHO_CLIENT_ID':'test-id', 'ZOHO_CLIENT_SECRET':'test-secret',
        'ZOHO_REFRESH_TOKEN':'test-private-refresh',
        'ZOHO_API_BASE_URL':'https://www.zohoapis.eu',
        'ZOHO_MODULE':'Custom_Claims', 'ZOHO_FIELD_REFERENCE':'Custom_Reference',
        'ZOHO_FIELD_STATUS':'Claim_Status',
    }.items():
        monkeypatch.setenv(key, value)


def test_real_disabled_by_default(monkeypatch):
    monkeypatch.setenv('ZOHO_MODE','mock')
    monkeypatch.setenv('ZOHO_REAL_ENABLED','NO')
    with pytest.raises(RuntimeError, match='disabled'):
        RealZohoClient()


def test_oauth_refresh_and_field_mapping(monkeypatch, caplog):
    settings(monkeypatch)
    history = []

    def handler(request):
        history.append((request.method, str(request.url), dict(request.headers)))
        if '/oauth/v2/token' in str(request.url):
            return httpx.Response(200, json={'access_token':'TOP-SECRET-TOKEN', 'expires_in':3600})
        if request.method == 'GET':
            return httpx.Response(200, json={'data':[{'id':'123456','Custom_Reference':'NCL-000001',
                'Claim_Status':'Open','Claimant_Name':'Alex Morgan'}], 'info': {'more_records':False}})
        if request.method == 'PUT':
            assert request.content == b'{"data":[{"Claim_Status":"Resolved"}]}'
            return httpx.Response(200, json={'data':[{'code':'SUCCESS'}]})
        raise AssertionError(str(request.url))

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        real = RealZohoClient(http_client=transport)
        with caplog.at_level(logging.INFO):
            rows = real.list_claims()
            record = real.update_status('123456','Resolved')
    assert rows[0]['Claim_Reference'] == 'NCL-000001'
    assert rows[0]['Status'] == 'Open'
    assert record['id'] == '123456'
    assert history[0][0] == 'POST'
    assert history[1][1].startswith('https://www.zohoapis.eu/crm/v8/Custom_Claims')
    assert 'TOP-SECRET-TOKEN' not in caplog.text
    assert 'test-private-refresh' not in caplog.text


def test_real_api_sanitised_error_and_allowlist(monkeypatch):
    settings(monkeypatch)
    monkeypatch.setenv('ZOHO_API_BASE_URL','https://attacker.example')
    with pytest.raises(ValueError, match='endpoint'):
        RealZohoClient()
    monkeypatch.setenv('ZOHO_API_BASE_URL','https://www.zohoapis.eu')
    def handler(req):
        if 'token' in str(req.url):
            return httpx.Response(200, json={'access_token':'secrettoken'})
        return httpx.Response(429, text='DO-NOT-LOG-TOKENS')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        real=RealZohoClient(http_client=client)
        with pytest.raises(CRMError) as error:
            real.list_claims()
    assert error.value.retryable is True
    assert 'DO-NOT-LOG-TOKENS' not in str(error.value)


def test_mock_record_is_local_and_editable():
    client = MockZohoClient(records=[{'id':'one','Status':'Open'}])
    assert client.update_status('one','Resolved')['Status'] == 'Resolved'
    with pytest.raises(CRMError):
        client.get_claim('missing')


def test_401_refresh_retry_once(monkeypatch):
    settings(monkeypatch)
    calls={'refresh':0,'crm':0}
    def handler(req):
        if '/oauth/v2/token' in str(req.url):
            calls['refresh'] += 1
            return httpx.Response(200, json={'access_token':'new-secret-'+str(calls['refresh'])})
        calls['crm'] += 1
        if calls['crm']==1:
            return httpx.Response(401, text='expired')
        return httpx.Response(200, json={'data':[], 'info': {'more_records':False}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = RealZohoClient(http_client=client)
        assert adapter.list_claims() == []
    assert calls == {'refresh':2,'crm':2}
