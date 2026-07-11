from app.persistence.session import normalize_database_url


def test_postgres_urls_use_psycopg3_driver() -> None:
    assert normalize_database_url("postgres://user:pass@db.example/app") == (
        "postgresql+psycopg://user:pass@db.example/app"
    )
    assert normalize_database_url("postgresql://user:pass@db.example/app?sslmode=require") == (
        "postgresql+psycopg://user:pass@db.example/app?sslmode=require"
    )


def test_explicit_sqlalchemy_driver_is_preserved() -> None:
    url = "postgresql+psycopg://user:pass@db.example/app"
    assert normalize_database_url(url) == url
