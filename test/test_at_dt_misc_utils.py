import pytest
import json
import pypeerassets.at.dt_misc_utils as mu
from pypeerassets.provider import RpcNode

settingsfile = open("settings.json", "r")
credentials = json.load(settingsfile)

PROVIDER = RpcNode(testnet=True, username=credentials["rpcuser"], password=credentials["rpcpass"], ip=None, port=credentials["port"], directory=None)
DECK_ID = "617005e36d23794763521ac3bad6d53a0ad6ee4259c8e45d8e81cdd09d67d595" # epoch length 22 blocks
DECK_P2TH = "mg5tRy8UUD5H1pwiyZnjeNzTdtfFrX6d1n"

def test_import_p2th_address():
    p2th_addr = DECK_P2TH
    importtest = mu.import_p2th_address(PROVIDER, p2th_addr)

def test_import_incorrect_p2th_address():
    with pytest.raises(ValueError):
        p2th_addr = "Fg5tRy8UUD5H1pwiyZnjeNzTdtfFrX6d1n" # incorrect address
        importtest = mu.import_p2th_address(PROVIDER, p2th_addr)

def test_deck_p2th_from_id():
    deck_id = DECK_ID
    dtest = mu.deck_p2th_from_id("tppc", deck_id)
    assert dtest == DECK_P2TH
