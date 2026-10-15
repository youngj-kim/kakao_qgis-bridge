"""Nullable KRW fare values shared by route responses and history files."""
FARE_FIELDS = (("toll_fare", "통행료"), ("taxi_fare", "예상 택시요금"))


def fare_amount(value):
    """Unknown is None; an explicit zero is a known free fare."""
    if value is None:
        return None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 <= value <= 2147483647 or value != int(value)):
        raise ValueError("요금은 원 단위의 0 이상 정수여야 합니다.")
    return int(value)
