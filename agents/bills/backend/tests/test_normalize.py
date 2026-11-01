import pytest

from bills_agent.detection.normalize import normalize_payee


@pytest.mark.parametrize(
    "raw, display",
    [
        ("AMZN Mktp US*2K4LM", "Amazon"),
        ("AMAZON PRIME*8RT21Q", "Amazon Prime"),
        ("NETFLIX.COM", "Netflix"),
        ("SQ *GREENLEAF LAWN", "Greenleaf Lawn"),
        ("GREENLEAF LAWN CARE LLC", "Greenleaf Lawn Care"),
        ("PP*MYFITPLAN 4029357733", "Myfitplan"),
        ("AUSTIN ENERGY ONLINE PMT", "Austin Energy"),
        ("CITY OF SPRINGFIELD UTIL WATER", "City of Springfield Util Water"),
        ("HULU 877-8244858", "Hulu"),
        ("VZWRLSS*APOCC VISB", "Verizon Wireless"),
        ("VERIZON FIOS", "Verizon Fios"),
        ("COMCAST CABLE COMM", "Xfinity"),
        ("MCAFEE*RENEWAL 8MXQ", "Mcafee"),
        ("TST* MAIN ST DINER", "Main St Diner"),
        ("ACME HOME WARRANTY AUSTIN TX", "Acme Home Warranty Austin"),
    ],
)
def test_display_names(raw, display):
    assert normalize_payee(raw).display == display


def test_similar_names_stay_apart():
    assert normalize_payee("VERIZON WIRELESS").key != normalize_payee("VERIZON FIOS").key
    water = normalize_payee("CITY OF SPRINGFIELD UTIL WATER").key
    assert water != normalize_payee("CITY OF SPRINGFIELD UTIL TRASH").key


def test_merchant_name_is_preferred():
    assert normalize_payee("NFLX 8KJ3 LOS GATOS", merchant_name="Netflix").display == "Netflix"
