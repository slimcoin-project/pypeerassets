import pytest
from .at_dt_test_settings import PROVIDER, DT_DECK_OBJ, PST

# init_parser
# force_dstates
# get_sdp_cards
# get_sdp_balances
# update_approved_proposals
# update_valid_ending_proposals

pytest.skip("Has errors, postponed to later betas.", allow_module_level=True)

def test_get_sdp_balances():
    # from pst needs: pst.epoch, pst.deck.epoch_length, pst.sdp_cards
    cards = PST.get_sdp_balances()
    assert len(cards) == 2 # We have 1 card bundle with 3 transfers, 1 is invalid (it goes to the deck issuer)

# get_tracked_txes

def test_get_tracked_txes_proposal():
    txes = PST.get_tracked_txes("proposal", min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_tracked_txes_locking():
    txes = PST.get_tracked_txes("locking", min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_tracked_txes_donation():
    txes = PST.get_tracked_txes("donation", min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_tracked_txes_signalling():
    txes = PST.get_tracked_txes("signalling", min_blockheight=0, max_blockheight=484163)
    assert len(txes) == 1

def test_get_tracked_txes_voting():
    txes = PST.get_tracked_txes("voting", min_blockheight=0, max_blockheight=484169)
    assert len(txes[PROPOSAL_TXID]["negative"]) == 1
    assert len(txes[PROPOSAL_TXID]["positive"]) == 1

# validate_proposer_issuance(self, dtx_id, card_units, card_sender, card_blocknum)
# validate_donation_issuance(self, dtx_id, card_units, card_sender)
# remove_invalid_cards(cards) -> static method
# check_card(self, card, issued_amount=None)
# epoch_init(self)
# epoch_postprocess(self, valid_epoch_cards)
# process_cardless_epochs(self, start, end)

"""def test_get_votes(): # method was removed, as it's now part of the ProposalState structure.
    # from pst needs: pst.voting_txes, pst.enabled_voters
    # from proposal needs: proposal.first_ptx.txid
    proposal = PST_PROPOSAL
    epoch = 20000
    votes = PST.get_votes(pst, proposal, epoch)
    assert votes == { "positive" : 9, "negative" : 5 }
    """
