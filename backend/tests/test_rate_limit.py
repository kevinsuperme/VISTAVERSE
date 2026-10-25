from app.rate_limit import check_auth_rate_limit


def test_auth_rate_limit_allows_bounded_requests_then_returns_retry(monkeypatch):
    import app.rate_limit as rate_limit

    rate_limit._hits.clear()
    monkeypatch.setattr(rate_limit, "_LIMITS", {"/api/auth/login": 2})
    assert check_auth_rate_limit("/api/auth/login", "client") is None
    assert check_auth_rate_limit("/api/auth/login", "client") is None
    retry = check_auth_rate_limit("/api/auth/login", "client")
    assert isinstance(retry, int) and retry >= 1


def test_auth_rate_limit_isolated_by_path_and_client(monkeypatch):
    import app.rate_limit as rate_limit

    rate_limit._hits.clear()
    monkeypatch.setattr(rate_limit, "_LIMITS", {"/api/auth/login": 1})
    assert check_auth_rate_limit("/api/auth/register", "client") is None
    assert check_auth_rate_limit("/api/auth/login", "other") is None
