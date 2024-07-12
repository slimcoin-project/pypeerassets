import pytest
import pypeerassets.at.dt_parser_utils as pu
from decimal import Decimal
from .at_dt_test_settings import PROVIDER, DT_DECK_OBJ, DT_DECK_ID, PST
from .at_dt_dummy_classes import TestObj


# tests dt_parser_utils
# Note: These tests need a running client daemon (peercoind, slimcoind).

def test_get_marked_txes():
    p2th_account = DT_DECK_ID + "PROPOSAL"
    txes = pu.get_marked_txes(PROVIDER, p2th_account, min_blockheight=0, max_blockheight=400000)
    assert len(txes) == 14

def test_get_proposal_states():
    states = pu.get_proposal_states(PROVIDER, DT_DECK_OBJ, current_blockheight=400000, all_signalling_txes=None, all_donation_txes=None)
    assert len(states) == 14

### from here on, tests do not need Provider / mandatory on-chain transactions ###

def test_get_sdp_weight():
    epochs_from_start = 7
    sdp_periods = 9
    weight = pu.get_sdp_weight(epochs_from_start, sdp_periods)
    assert weight == Decimal("0.22")

def test_update_voters():
    # new_cards = pu.get_sdp_balances(s.PST)
    # new_cards = PST.get_sdp_balances() # TODO: better mock this

    # new cards: new voter issues new coins, old voter sends 5 coins to another new voter, one has unchanged.
    new_cards = [
    TestObj(amount=[20], sender="miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353", receiver=["miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353"], type="CardIssue"),
    TestObj(amount=[5], sender="mybLEsXFH6emUt54bS3tci45d8vakZhdVT", receiver=["mgp8yva7tgLDPXe1tseMZtpT7fybzu5vFq"], type="CardTransfer")
    ]

    print(new_cards)

    # NOTE: The amounts are raw (int numbers), i.e. to get the "human-readable" amount you have to do the following:
    # 10**deck.number_of_decimals

    old_voters = {"mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X" : 50, "mybLEsXFH6emUt54bS3tci45d8vakZhdVT" : 20}
    newvoters = pu.update_voters(voters=old_voters, new_cards=new_cards, weight=1)
    assert newvoters == {"mgp8yva7tgLDPXe1tseMZtpT7fybzu5vFq" : 5, "mybLEsXFH6emUt54bS3tci45d8vakZhdVT" : 15, "miC3Vsh2WeZzmrzCRJuu5T7q9snvGvB353" : 20, "mnm7c3LcfkZGSwHZXpDBAZc67ugUgd3E3X" : 50}





# following test is on hold because it needs a new set of transactions.
"""
def test_get_valid_ending_proposals():
    # from pst needs: pst.proposal_states (with several attributes from each state), pst.epoch, deck.epoch_length, pst.enabled_voters
    proposals = pu.get_valid_ending_proposals(pst, EXAMPLE_DECK)
    assert proposals == {}

"""


