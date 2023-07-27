import pytest
import pypeerassets.at.extended_utils as eu
from typing import Generator
from .at_dt_dummy_classes import DummyATCard

# The following cards correspond to real AT/PoB token cards in the 2023 testnet blockchain.
valid_card_lsimple = DummyATCard(txid="fc48be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0", amount=12000000, donation_txid="3016e6fea3bf9288b61ebbc378530f73351df8be470f37ffa754187d70e9a6e9", number_of_decimals=2, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=132465, blockseq=1, cardseq=0, ctype="CardIssue")
valid_card_lbundle1 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=540000, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=1, ctype="CardIssue")
valid_card_lbundle2 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=7460000, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=0, ctype="CardIssue")

# This bundle uses the correct amount in card 1, but an incorrect one in card 2. This should make both cards invalid.
invalid_card_lwrongamount_bundle1 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=540000, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=1, ctype="CardIssue")
invalid_card_lwrongamount_bundle2 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=7460001, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=1, ctype="CardIssue")

# CardTransfer is completely fabricated.
valid_ctransfer_lx = DummyATCard(txid="0048be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0", amount=15000, donation_txid=None, number_of_decimals=2, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=135000, blockseq=1, cardseq=0, ctype="CardTransfer")

# TODO: add unittests with invalid cards
# get_issuance_bundle(cards: list, i: int)
# parameters: cards=total list, i=index of card where bundle was detected
# returns: total_issued_amount, last_processed_position
def test_get_issuance_bundle():
    total_issued_amount, last_processed_position = eu.get_issuance_bundle([valid_card_lsimple, valid_card_lbundle1, valid_card_lbundle2], 1)
    assert total_issued_amount == 8000000
    assert last_processed_position == 2

# process_cards_by_bundle(cards, debug: bool=False):
def test_process_cards_by_bundle():
    card_bundles = eu.process_cards_by_bundle([valid_card_lsimple, valid_card_lbundle1, valid_card_lbundle2])
    assert isinstance(card_bundles, Generator)
    card_bundle_list = list(card_bundles)
    assert len(card_bundle_list) == 3 # unchanged
    assert card_bundle_list[0][0].amount ==  [12000000]
    assert card_bundle_list[1][0].amount == [540000]
    assert card_bundle_list[2][0].amount == [7460000]
    assert card_bundle_list[0][1] == None
    assert card_bundle_list[1][1] == 8000000
    assert card_bundle_list[2][1] == None

def test_process_cards_by_bundle_with_cardtransfer():
    card_bundles = eu.process_cards_by_bundle([valid_card_lsimple, valid_card_lbundle1, valid_card_lbundle2, valid_ctransfer_lx])
    card_bundle_list = list(card_bundles)
    assert len(card_bundle_list) == 4 # unchanged
    assert card_bundle_list[3][0].amount == [15000]
    assert card_bundle_list[3][1] == None



