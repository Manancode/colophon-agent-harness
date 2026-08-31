"""A server that listens beyond loopback must be able to tell callers apart.

The default host is loopback, and on loopback no token is required: nothing
off-machine can reach the port, so there is nobody to authenticate. The moment
the bind address stops being loopback that argument collapses, and what is
exposed is not a read-only surface — these tools write files and run a
renderer.

So a non-loopback bind requires a token, and a token that cannot be enforced
stops the server rather than starting it unprotected. Both exits are
``SystemExit``, which is what a misconfigured launch should be: loud, early,
and before the socket exists.
"""

from __future__ import annotations

import pytest

from colophon import mcp_server
from colophon import sandbox


@pytest.fixture(autouse=True)
def clean_startup(monkeypatch):
    """Never inherit a token or a root from the environment or a prior test."""
    monkeypatch.delenv(mcp_server.TOKEN_ENV, raising=False)
    monkeypatch.delenv(sandbox.ROOT_ENV, raising=False)
    sandbox.reset()
    yield
    sandbox.reset()


def fake_server(monkeypatch, calls: list[dict]):
    class _Fake:
        def run(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(mcp_server, "build_server", lambda token=None: _Fake())
    monkeypatch.setattr(mcp_server, "build_auth", lambda token: object())


# --------------------------------------------------------------------------
# which addresses count as local
# --------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "127.0.0.53"])
def test_loopback_addresses_are_local(host):
    assert mcp_server.is_loopback(host) is True


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "not-a-host"])
def test_non_loopback_addresses_are_not_local(host):
    assert mcp_server.is_loopback(host) is False


def test_localhost_is_local_only_when_it_resolves_to_loopback(monkeypatch):
    """Resolved, not assumed.

    A host whose resolver points `localhost` at a public address gets no
    loopback exemption, because on that machine it is not loopback.
    """
    import socket

    def resolving_to(*addresses):
        return lambda *a, **k: [(socket.AF_INET, 0, 0, "", (addr, 0)) for addr in addresses]

    monkeypatch.setattr(socket, "getaddrinfo", resolving_to("127.0.0.1"))
    assert mcp_server.is_loopback("localhost") is True

    monkeypatch.setattr(socket, "getaddrinfo", resolving_to("127.0.0.1", "93.184.216.34"))
    assert mcp_server.is_loopback("localhost") is False


def test_a_host_that_cannot_be_resolved_is_not_trusted(monkeypatch):
    import socket

    def boom(*a, **k):
        raise OSError("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)

    assert mcp_server.is_loopback("localhost") is False


# --------------------------------------------------------------------------
# refusing an open bind
# --------------------------------------------------------------------------


def test_binding_to_all_interfaces_without_a_token_is_refused(monkeypatch):
    calls: list[dict] = []
    fake_server(monkeypatch, calls)

    with pytest.raises(SystemExit) as caught:
        mcp_server.serve(host="0.0.0.0")

    assert "refusing to bind" in str(caught.value)
    assert mcp_server.TOKEN_ENV in str(caught.value)
    assert calls == []  # nothing was ever listening


def test_binding_to_a_lan_address_without_a_token_is_refused(monkeypatch):
    fake_server(monkeypatch, [])

    with pytest.raises(SystemExit):
        mcp_server.serve(host="192.168.1.10")


def test_an_unparseable_host_is_treated_as_remote(monkeypatch):
    """A name we cannot read as an address might resolve anywhere."""
    fake_server(monkeypatch, [])

    with pytest.raises(SystemExit):
        mcp_server.serve(host="colophon.internal")


# --------------------------------------------------------------------------
# what a token buys
# --------------------------------------------------------------------------


def test_a_token_lets_the_server_bind_beyond_loopback(monkeypatch):
    calls: list[dict] = []
    fake_server(monkeypatch, calls)

    mcp_server.serve(host="0.0.0.0", token="s3cret")

    assert calls[0]["host"] == "0.0.0.0"


def test_the_token_may_come_from_the_environment(monkeypatch):
    calls: list[dict] = []
    fake_server(monkeypatch, calls)
    monkeypatch.setenv(mcp_server.TOKEN_ENV, "from-env")

    mcp_server.serve(host="0.0.0.0")

    assert calls[0]["host"] == "0.0.0.0"


def test_loopback_needs_no_token(monkeypatch):
    calls: list[dict] = []
    fake_server(monkeypatch, calls)

    mcp_server.serve(host="127.0.0.1")

    assert calls[0]["host"] == "127.0.0.1"


def test_the_token_reaches_the_layer_that_checks_it(monkeypatch):
    """A token that never gets to the auth layer is a token that does nothing."""
    seen: list[object] = []

    class _Fake:
        def run(self, **kwargs):
            pass

    def _record(token=None):
        seen.append(token)
        return _Fake()

    monkeypatch.setattr(mcp_server, "build_server", _record)

    mcp_server.serve(host="127.0.0.1", token="s3cret")

    assert seen == ["s3cret"]


# --------------------------------------------------------------------------
# failing closed
# --------------------------------------------------------------------------


def test_a_server_that_cannot_check_tokens_does_not_start(monkeypatch):
    """Fail closed. Starting anyway would be the vulnerability itself.

    The failure has to come from building the *server*, which is where the
    auth provider is constructed — a fake that skips that step would make
    this test pass against a server that never checks anything.
    """
    calls: list[dict] = []

    def _broken(token=None):
        raise TypeError("unsupported fastmcp version")

    class _Fake:
        def run(self, **kwargs):
            calls.append(kwargs)

    def _server(token=None):
        mcp_server.build_auth(token)  # the real construction, as in serve()
        return _Fake()

    monkeypatch.setattr(mcp_server, "build_auth", _broken)
    monkeypatch.setattr(mcp_server, "build_server", _server)

    with pytest.raises(SystemExit) as caught:
        mcp_server.serve(host="0.0.0.0", token="s3cret")

    assert "refusing to start" in str(caught.value)
    assert calls == []


def test_an_empty_token_counts_as_no_token(monkeypatch):
    """`token="" `is what `or` quietly produces. It must not read as a token."""
    calls: list[dict] = []
    fake_server(monkeypatch, calls)

    with pytest.raises(SystemExit) as caught:
        mcp_server.serve(host="0.0.0.0", token="")

    assert "refusing to bind" in str(caught.value)
    assert calls == []
