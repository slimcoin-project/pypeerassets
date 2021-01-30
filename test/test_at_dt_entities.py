import pytest
import pypeerassets.at.dt_entities as e

# Note: These tests need a running client daemon (peercoind, slimcoind).
# To conduct these tests, you need to rename the settings.default.json to settings.json.
# Then store your rpcuser, rpcpassword and port (default 9904) in this file.
# Take them from the cryptocurrency configuration file, e.g. peercoin.conf or slimcoin.conf.

settingsfile = open("settings.json", "r")
credentials = json.load(settingsfile)

PROVIDER = RpcNode(testnet=True, username=credentials["rpcuser"], password=credentials["rpcpass"], ip=None, port=credentials["port"], directory=None)

def test_tracked_transaction_from_json():
    deck = ""
    
    tx = e.TrackedTransaction.from_json(cls, tx_json, provider)
    assert type(TrackedTransaction) == 
    
