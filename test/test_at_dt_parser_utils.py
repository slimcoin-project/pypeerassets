import pytest
import pypeerassets.at.dt_parser_utils as pu
import json
from decimal import Decimal
from pypeerassets.provider import RpcNode
from pypeerassets.pautils import deck_from_tx
from pypeerassets.__main__ import find_all_valid_cards

# Note: These tests need a running client daemon (peercoind, slimcoind).
# To conduct these tests, you need to rename the settings.default.json to settings.json.
# Then store your rpcuser, rpcpassword and port (default 9904) in this file.
# Take them from the cryptocurrency configuration file, e.g. peercoin.conf or slimcoin.conf.

class TestObj(object):
   """Minimal test object to fill with keyword arguments. Mostly used for TrackedTransactions."""
   def __init__(self, **kwargs):
       for k, v in kwargs.items():
           setattr(self, k, v)

settingsfile = open("settings.json", "r")
credentials = json.load(settingsfile)

PROVIDER = RpcNode(testnet=True, username=credentials["rpcuser"], password=credentials["rpcpass"], ip=None, port=credentials["port"], directory=None)
DECK_ID = "617005e36d23794763521ac3bad6d53a0ad6ee4259c8e45d8e81cdd09d67d595" # epoch length 22 blocks
DECK_P2TH = "mg5tRy8UUD5H1pwiyZnjeNzTdtfFrX6d1n"
DECK_OBJ = deck_from_tx(DECK_ID, PROVIDER)
P2TH_DONATION = DECK_OBJ.derived_p2th_address("donation")
P2TH_LOCKING = DECK_OBJ.derived_p2th_address("locking")
P2TH_SIGNALLING = DECK_OBJ.derived_p2th_address("signalling")
P2TH_PROPOSAL = DECK_OBJ.derived_p2th_address("proposal")
P2TH_VOTING = DECK_OBJ.derived_p2th_address("voting")
pu.import_p2th_address(PROVIDER, P2TH_DONATION)
pu.import_p2th_address(PROVIDER, P2TH_LOCKING)
pu.import_p2th_address(PROVIDER, P2TH_SIGNALLING)
pu.import_p2th_address(PROVIDER, P2TH_PROPOSAL)
pu.import_p2th_address(PROVIDER, P2TH_VOTING)

PROPOSAL_TXID = "697a33f5fdeeef1d136e342ecce6f42dd7aa16a3eb57b6f9273c5692dec74799"
SDP_DECK_ID = "7ffb89b247a91cc1759885442bacfdbbaf27d1a3329d998abc5072f8ef3ea110"
SDP_DECK_OBJ = deck_from_tx(SDP_DECK_ID, PROVIDER)

PST_PROPOSAL = TestObj(all_donation_txes = [], all_signalling_txes = [], all_locking_txes = [], first_ptx = TestObj(txid = PROPOSAL_TXID))
SDP_CARDS = find_all_valid_cards(PROVIDER, SDP_DECK_OBJ)
NEGTX = [ TestObj(sender = "mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X", epoch=20000), TestObj(sender = "mybLEsXFH6emUt54bS3tci45d8vakZhdVT", epoch=19000) ]
POSTX = [ TestObj(sender = "miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353", epoch=20000)]
VOTINGTX = { PROPOSAL_TXID : { "negative" : NEGTX, "positive" : POSTX }}
VOTERS = {"mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X" : 5, "mybLEsXFH6emUt54bS3tci45d8vakZhdVT" : 5, "miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353" : 9}
PST = TestObj(proposal_states={PROPOSAL_TXID: PST_PROPOSAL}, deck=DECK_OBJ, epoch=22008, sdp_cards=list(SDP_CARDS), voting_transactions = VOTINGTX, enabled_voters=VOTERS)


def test_import_p2th_address():
    p2th_addr = DECK_P2TH
    importtest = pu.import_p2th_address(PROVIDER, p2th_addr)

def test_import_incorrect_p2th_address():
    with pytest.raises(ValueError):
        p2th_addr = "Fg5tRy8UUD5H1pwiyZnjeNzTdtfFrX6d1n" # incorrect address
        importtest = pu.import_p2th_address(PROVIDER, p2th_addr)

def test_deck_p2th_from_id():
    deck_id = DECK_ID
    dtest = pu.deck_p2th_from_id("tppc", deck_id)
    assert dtest == DECK_P2TH

def test_get_marked_txes():
    p2th_account = P2TH_PROPOSAL
    txes = pu.get_marked_txes(PROVIDER, p2th_account, min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_donation_txes():
    txes = pu.get_donation_txes(PROVIDER, DECK_OBJ, PST, min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_locking_txes():
    # from pst needs: pst.proposal_states[tx.proposal_txid].all_donation_txes
    txes = pu.get_locking_txes(PROVIDER, DECK_OBJ, PST, min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 0

def test_get_signalling_txes():
    txes = pu.get_signalling_txes(PROVIDER, DECK_OBJ, PST, min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_voting_txes(): # does not need pst
    txes = pu.get_voting_txes(PROVIDER, DECK_OBJ, min_blockheight=0, max_blockheight=484169)
    assert len(txes[PROPOSAL_TXID]["negative"]) == 1
    assert len(txes[PROPOSAL_TXID]["positive"]) == 1

def test_get_proposal_states():
    states = pu.get_proposal_states(PROVIDER, DECK_OBJ, current_blockheight=484169, all_signalling_txes=None, all_donation_txes=None)
    print(states)
    assert len(states) == 1

### from here on, tests do not need Provider / mandatory on-chain transactions ###

def test_get_sdp_weight():
    epochs_from_start = 7
    sdp_periods = 9
    weight = pu.get_sdp_weight(epochs_from_start, sdp_periods)
    assert weight == Decimal("0.22")

def test_get_sdp_balances():
    # from pst needs: pst.epoch, pst.deck.epoch_length, pst.sdp_cards
    cards = pu.get_sdp_balances(PST)
    assert len(cards) == 2 # We have 1 card bundle with 3 transfers, 1 is invalid (it goes to the deck issuer)

def test_update_voters():
    new_cards = pu.get_sdp_balances(PST)
    # The "old list" contains one voter (mybLEsXFH6emUt54bS3tci45d8vakZhdVT) who gets 3.1 more cards in the new_cards list, while the other "old voter" (mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X) with 5 votes does not.
    # Theres is an additional voter in new_cards ().
    # NOTE: The amounts are raw (int numbers), i.e. to get the "human-readable" amount you have to do the following:
    # 10**deck.number_of_decimals

    old_voters = {"mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X" : 50, "mybLEsXFH6emUt54bS3tci45d8vakZhdVT" : 20}
    newvoters = pu.update_voters(voters=old_voters, new_cards=new_cards, weight=0.1)
    assert newvoters == {"mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X" : 5, "mybLEsXFH6emUt54bS3tci45d8vakZhdVT" : 5, "miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353" : 9}


def test_get_votes():
    # from pst needs: pst.voting_transactions, pst.enabled_voters
    # from proposal needs: proposal.first_ptx.txid
    pst = PST
    proposal = PST_PROPOSAL
    epoch = 20000
    votes = pu.get_votes(pst, proposal, epoch)
    assert votes == { "positive" : 9, "negative" : 5 }


# following test is on hold because it needs a new set of transactions.
"""
def test_get_valid_ending_proposals():
    # from pst needs: pst.proposal_states (with several attributes from each state), pst.epoch, deck.epoch_length, pst.enabled_voters
    proposals = pu.get_valid_ending_proposals(pst, EXAMPLE_DECK)
    assert proposals == {}

"""


