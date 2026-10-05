"""find_institution: ievade nekļūst par SQL daļu (OWASP A05)."""

from app import storage


def test_find_institution_known_code():
    storage.reset(seed=False)
    assert storage.find_institution("VCD") == {
        "code": "VCD",
        "name": "Valsts ceļu dienests (izdomāts)",
    }


def test_find_institution_unknown_code():
    storage.reset(seed=False)
    assert storage.find_institution("NAV") is None


def test_find_institution_sql_injection_returns_nothing():
    storage.reset(seed=False)
    assert storage.find_institution("X' OR '1'='1") is None
    assert storage.find_institution("VCD' --") is None
