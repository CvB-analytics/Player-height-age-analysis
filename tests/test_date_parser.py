from src.parser.date_parser import detect_date_order, parse_date


def test_detects_dmy_from_unambiguous_value():
    assert detect_date_order(["13/03/08", "04/07/09"]) == "DMY"
    assert parse_date("04/07/09", "DMY").isoformat() == "2009-07-04"


def test_detects_mdy_from_unambiguous_value():
    assert detect_date_order(["12/31/08", "04/07/09"]) == "MDY"
    assert parse_date("04/07/09", "MDY").isoformat() == "2009-04-07"


def test_iso_and_ambiguous_dataset():
    assert detect_date_order(["2008-03-13"]) == "YMD"
    assert parse_date("2008-03-13", "YMD").isoformat() == "2008-03-13"
    assert detect_date_order(["04/07/09", "03/08/10"]) == "AMBIGUOUS"
    assert detect_date_order(["13/03/08", "12/31/08"]) == "AMBIGUOUS"


def test_invalid_calendar_date_is_rejected():
    assert parse_date("31/02/2008", "DMY") is None


def test_month_names():
    assert parse_date("13 Mar 2008").isoformat() == "2008-03-13"
    assert parse_date("March 13 2008").isoformat() == "2008-03-13"
