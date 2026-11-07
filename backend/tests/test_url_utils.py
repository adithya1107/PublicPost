import re
import socket

import pytest

from app.url_utils import (
    article_id,
    clean_article_url,
    clean_image_url,
    is_public_url,
    normalise_url,
)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "not a url",
        "ftp://example.com/a",
        "javascript:alert(1)",
        "mailto:a@example.com",
        "https://",
        "https://user:pass@example.com/a",
        "http://[bad",
    ],
)
def test_unusable_links_are_rejected(raw: str | None) -> None:
    assert clean_article_url(raw) is None
    assert clean_image_url(raw) is None


def test_tracking_parameters_and_fragments_are_removed() -> None:
    url = "https://www.bbc.co.uk/news/a?at_medium=RSS&at_campaign=rss&utm_source=x&id=7#publisher=newsstand"
    assert clean_article_url(url) == "https://www.bbc.co.uk/news/a?id=7"


def test_spaces_and_non_ascii_are_encoded_without_double_encoding() -> None:
    assert clean_article_url("https://example.com/café au lait") == "https://example.com/caf%C3%A9%20au%20lait"
    assert clean_article_url("https://example.com/a%20b") == "https://example.com/a%20b"


def test_international_hostnames_are_converted() -> None:
    assert clean_article_url("https://bücher.example/a") == "https://xn--bcher-kva.example/a"


def test_custom_ports_are_kept_and_default_ports_dropped() -> None:
    assert clean_article_url("https://example.com:8443/a") == "https://example.com:8443/a"
    assert clean_article_url("https://example.com:443/a") == "https://example.com/a"


def test_url_with_no_host_is_not_public() -> None:
    assert is_public_url("not-a-url") is False


def test_image_links_are_upgraded_to_https() -> None:
    assert clean_image_url("http://p.imgci.com/a.jpg") == "https://p.imgci.com/a.jpg"


def test_signed_image_queries_are_left_alone() -> None:
    url = "https://i.guim.co.uk/a.jpg?width=460&quality=85&auto=format&fit=max&s=abc123&utm_source=keep"
    assert clean_image_url(url) == url


@pytest.mark.parametrize(
    "variant",
    [
        "https://Example.com/story/",
        "http://example.com/story",
        "https://example.com:443/story",
        "https://example.com/story?utm_source=rss",
        "https://example.com/story#comments",
    ],
)
def test_url_variants_get_the_same_id(variant: str) -> None:
    expected = article_id(clean_article_url("https://example.com/story"))
    assert article_id(clean_article_url(variant)) == expected


def test_query_order_does_not_change_the_id() -> None:
    assert normalise_url("https://e.com/s?b=2&a=1") == normalise_url("https://e.com/s?a=1&b=2")


def test_different_stories_get_different_ids() -> None:
    assert article_id("https://e.com/s?id=1") != article_id("https://e.com/s?id=2")


def test_id_is_16_lowercase_hex_characters() -> None:
    assert re.fullmatch(r"[0-9a-f]{16}", article_id("https://example.com/story"))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ],
)
def test_private_addresses_are_not_public(url: str) -> None:
    assert is_public_url(url) is False


def test_hostname_that_resolves_to_a_private_address_is_not_public(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("10.1.2.3", 0))])
    assert is_public_url("https://sneaky.example/") is False


def test_unresolvable_hostname_is_not_public(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    assert is_public_url("https://missing.example/") is False


def test_public_address_is_public(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 0))])
    assert is_public_url("https://example.com/") is True
