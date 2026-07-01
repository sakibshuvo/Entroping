from entroping.core.known_failures import normalize_known_failure_test


def test_normalize_known_failure_test_trims_and_uses_posix_separators() -> None:
    assert normalize_known_failure_test(" tests\\checkout.hurl \n") == "tests/checkout.hurl"
