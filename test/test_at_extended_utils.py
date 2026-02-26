import pytest
import pypeerassets.at.extended_utils as eu
from typing import Generator
from .at_dt_dummy_classes import DummyATCard
from pypeerassets.protocol import Deck, CardTransfer, IssueMode

TESTDECK = Deck(name="TestDeckAT1",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            asset_specific_data=b'\x10\x02@dJ\x14@\xf1c\xa4\xd0\xa8\xbcD\xb4\xba\x00\xb9T\xc2\xbd\xbe\xfb\x87|\xf4P\x02') # same as "official" Testnet PoB token

# Some data was taken from real AT/PoB token cards in the 2023+ testnet blockchain.
# Following CardIssue is not part of a bundle
valid_card_lsimple = CardTransfer(deck=TESTDECK,
                                  txid="fc48be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0",
                                  amount=[12000000],
                                  receiver=["mnTT7YDCTgfUrp16KgTweTwTr1FXFsx1tk"],
                                  donation_txid="3016e6fea3bf9288b61ebbc378530f73351df8be470f37ffa754187d70e9a6e9",
                                  number_of_decimals=2,
                                  sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb",
                                  blocknum=132465,
                                  blockseq=1,
                                  cardseq=0,
                                  type="CardIssue")
# Following 2 CardIssues are part of a bundle
valid_card_lbundle1 = CardTransfer(deck=TESTDECK,
                                   txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94",
                                   amount=[540000],
                                   receiver=["msLtP3b3o1GarXJ5HVNBWKynkPyRoevNiA"],
                                   donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8",
                                   number_of_decimals=2,
                                   sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz",
                                   blocknum=132499,
                                   blockseq=1,
                                   cardseq=1,
                                   type="CardIssue")
valid_card_lbundle2 = CardTransfer(deck=TESTDECK,
                                   txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94",
                                   amount=[7460000],
                                   receiver=["n2xTjHADUUpWZDfDdoCPJjmgFPSDWsGxys"],
                                   donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8",
                                   number_of_decimals=2,
                                   sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz",
                                   blocknum=132499,
                                   blockseq=1,
                                   cardseq=0,
                                   type="CardIssue")
# CardTransfer, not part of a bundle
valid_ctransfer_lx = CardTransfer(deck=TESTDECK,
                                  txid="0048be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0",
                                  amount=[15000],
                                  receiver=["moFQhbxDKJ7Gxs1GVXFQi9LWzQPMwNxoLM"],
                                  donation_txid=None,
                                  number_of_decimals=2,
                                  sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb",
                                  blocknum=135000,
                                  blockseq=1,
                                  cardseq=0,
                                  type="CardTransfer")


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
