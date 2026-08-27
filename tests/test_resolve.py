import os

from abf.intent import canonicalize_target


def test_dotdot_normalizes_before_binding():
    assert canonicalize_target("acct/../payroll/secret") == "payroll/secret"


def test_unexpanded_env_fails_closed():
    try:
        canonicalize_target("$HOME/project")
    except ValueError as exc:
        assert "unexpanded" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_env_expansion_then_normalize():
    assert canonicalize_target("$ROOT/acct/../acct/1", env={"ROOT": "/data"}) == "/data/acct/1"


def test_alias_then_normalize():
    assert canonicalize_target("docs", aliases={"docs": "/var/lib/docs"}) == "/var/lib/docs"


def test_symlink_followed_when_present(tmp_path):
    real = tmp_path / "real"
    link = tmp_path / "link"
    real.mkdir()
    os.symlink(real, link)
    assert canonicalize_target(str(link)) == str(real.resolve())
