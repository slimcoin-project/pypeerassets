import pytest
import json
import pypeerassets.at.dt_misc_utils as mu
from pypeerassets.provider import RpcNode
from pypeerassets.at.dt_parser_utils import deck_from_tx

settingsfile = open("settings.json", "r")
credentials = json.load(settingsfile)

PROVIDER = RpcNode(testnet=True, username=credentials["rpcuser"], password=credentials["rpcpass"], ip=None, port=credentials["port"], directory=None)
DECK_ID = "617005e36d23794763521ac3bad6d53a0ad6ee4259c8e45d8e81cdd09d67d595" # epoch length 22 blocks
DECK_ID2 = "4151f408a453af433ba1239ed8be8c9a549234980c7c053f3255ea7988b07d00" # longer deck for public testing
DECK_P2TH = "mg5tRy8UUD5H1pwiyZnjeNzTdtfFrX6d1n"
INPUT_TXID = "3141e44dffdb4b2e2c4a3fb79052b9701423ba843aa5fd722ae9ef36c79c7fe8"
PROPOSAL_TXID = "de93886ccc841e13f7559dc54851b3c46b41f7c5ebd806840439326a13fae421"

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

def test_create_unsigned_tx_signalling_manual():
    # manually selecting input.
    deck = deck_from_tx(DECK_ID2, PROVIDER)
    dstr = b"DS" + bytes.fromhex(PROPOSAL_TXID)
    unsigned = mu.create_unsigned_tx(deck, input_txid=INPUT_TXID, input_vout=2, address="mmiUdqJTBtUc5hCGVYLPnqtNivsWSEZuoq", amount=444444, provider=PROVIDER, tx_type="signalling", data=dstr)
    print(unsigned)

def test_create_unsigned_tx_signalling_auto():
    # Using peerassets feature to select a suitable input. TODO: Not working properly, doesn't find the output.
    deck = deck_from_tx(DECK_ID2, PROVIDER)
    dstr = b"DS" + bytes.fromhex(PROPOSAL_TXID)
    unsigned = mu.create_unsigned_tx(deck, input_address="n18j5ESg1Lz7Z1N4ZwTttjGVjBDNXbgbch", address="mmiUdqJTBtUc5hCGVYLPnqtNivsWSEZuoq", amount=444444, provider=PROVIDER, tx_type="signalling", data=dstr)
    print(unsigned)
