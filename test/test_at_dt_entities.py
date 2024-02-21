import json
import pytest
import pypeerassets.at.dt_entities as e
import pypeerassets.provider.slm_rpcnode as n

# Note: These tests need a running client daemon (peercoind, slimcoind).
# To conduct these tests, you need to rename the settings.default.json to settings.json.
# Then store your rpcuser, rpcpassword and port (default 9904) in this file.
# Take them from the cryptocurrency configuration file, e.g. peercoin.conf or slimcoin.conf.

with open("./settings.json", "r") as settingsfile:
    credentials = json.load(settingsfile)

with open("./dt_dummy_txes.json", "r") as dummyfile:
    tx_dummies = json.load(dummyfile)
    # dummy txes are in this order in the dummyfile. All are valid.
    dummy_signalling, dummy_locking, dummy_donation, dummy_voting, dummy_proposal = tx_dummies


PROVIDER = n.SlmRpcNode(testnet=True, username=credentials["rpcuser"], password=credentials["rpcpass"], ip=None, port=credentials["port"], directory=None)


def test_signalling_transaction_from_json():
    tx = e.SignallingTransaction.from_json(dummy_signalling, PROVIDER)
    assert type(tx) == e.SignallingTransaction

def test_locking_transaction_from_json():
    tx = e.LockingTransaction.from_json(dummy_locking, PROVIDER)
    assert type(tx) == e.LockingTransaction

def test_donation_transaction_from_json():
    tx = e.DonationTransaction.from_json(dummy_donation, PROVIDER)
    assert type(tx) == e.DonationTransaction

def test_voting_transaction_from_json():
    tx = e.VotingTransaction.from_json(dummy_voting, PROVIDER)
    assert type(tx) == e.VotingTransaction

def test_proposal_transaction_from_json():
    tx = e.ProposalTransaction.from_json(dummy_proposal, PROVIDER)
    assert type(tx) == e.ProposalTransaction

