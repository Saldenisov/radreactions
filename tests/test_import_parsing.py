from import_reactions import parse_rate_value


def test_parse_rate_value_simple_float():
    assert parse_rate_value("1.23") == 1.23


def test_parse_rate_value_times_ten_power_ascii():
    assert parse_rate_value("5.5 x 10^9") == 5.5e9


def test_parse_rate_value_times_ten_power_unicode():
    assert parse_rate_value("6.2 × 10^4") == 6.2e4


def test_parse_rate_value_invalid_returns_none():
    assert parse_rate_value("not_a_number") is None
