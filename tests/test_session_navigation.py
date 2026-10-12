"""Regression checks: login cookie permits ordinary cross-site GET navigation."""


def test_admin_can_visit_pages_after_login(client):
    response = client.post(
        '/api/auth/login',
        json={'username': 'admin', 'password': 'NorthstarAdmin!2026'},
    )
    assert response.status_code == 200, response.text
    cookie = response.headers['set-cookie'].lower()
    assert 'nc_session=' in cookie
    assert 'samesite=lax' in cookie
    assert 'httponly' in cookie
    assert 'path=/' in cookie

    me = client.get('/api/auth/me')
    assert me.status_code == 200, me.text
    assert me.json()['role'] == 'Admin'

    for path in ('/', '/tickets', '/tickets/new', '/assets', '/users', '/docs'):
        page = client.get(path)
        assert page.status_code == 200, f'{path}: {page.status_code} {page.text[:200]}'


def test_protected_page_without_cookie_stays_protected(client):
    assert client.get('/tickets').status_code == 401
    assert client.get('/users').status_code == 401
    # Built-in Swagger UI remains public; its protected API calls need login.
    assert client.get('/docs').status_code == 200
