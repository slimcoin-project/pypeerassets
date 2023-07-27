import pytest
import json
import pypeerassets.at.at_parser as a
from .at_dt_dummy_classes import DummyATDeck, DummyATCard

with open("at_dummy_txes.json", "r") as dummyfile:
    tx_dummies = json.load(dummyfile)

# The block hashes and heights correspond to real blocks in the 2023 testnet blockchain.
block_dummies = [{"height" : 132463, "hash" : "0000bca5ab2f35deda8bca8e317a285933abb3d34c709749f0e3f46ea4860bee"},
                 {"height" : 132472, "hash" : "0000d4feb2f9270bd623273f8c5539b543506cf0a6dae6e5618a06197f97f4f7"},
                 {"height" : 50, "hash" : "000000bc97783912780624dcce85efce226f286f45b7ccc379be08928ac4709e"}]

class DummyProvider:
    def __init__(self):
        pass

    def getrawtransaction(self, txid, json_mode):
        assert json_mode == 1
        for tx in tx_dummies:
            if tx["txid"] == txid:
                return tx

    def getblock(self, blockhash):
        for b in block_dummies:
            if b["hash"] == blockhash:
                return b


# basic variables
provider = DummyProvider()

BURNADDR="mmSLiMCoinTestnetBurnAddress1XU5fu"
unlimited_deck = DummyATDeck(deckid="fb93cce7aceb9f7fda228bc0c0c2eca8c56c09c1d846a04bd6a59cae2a895974", at_address=BURNADDR, multiplier=100, startblock=None, endblock=None)
limited_deck = DummyATDeck(deckid="66c25ad60538a9de0a7895d833a4a3aeeacdd75b1db9c5dd69c3746dd21d39be", at_address=BURNADDR, multiplier=1000, startblock=132000, endblock=140000)

# The following cards correspond to real AT/PoB token cards in the 2023 testnet blockchain.
# unlimited deck card
valid_card_ul = DummyATCard(txid="97e82554217ff486343833c1e8c7629d459b9a831496091da46b4096d2523815", amount=5745000, donation_txid="6597c3fcba12db091d7104e29665eb2a1d740261c93e39a60d0487e7bc42b716", number_of_decimals=4, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=132356, blockseq=1, cardseq=0, ctype="CardIssue")
# limited deck cards
valid_card_lsimple = DummyATCard(txid="fc48be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0", amount=12000000, donation_txid="3016e6fea3bf9288b61ebbc378530f73351df8be470f37ffa754187d70e9a6e9", number_of_decimals=2, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=132465, blockseq=1, cardseq=0, ctype="CardIssue")
valid_card_lbundle1 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=540000, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=1, ctype="CardIssue")
valid_card_lbundle2 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=7460000, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=0, ctype="CardIssue")

invalid_card_lwrongblock = DummyATCard(txid="fab00095925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0", amount=12000000, donation_txid="fab000fea3bf9288b61ebbc378530f73351df8be470f37ffa754187d70e9a6e8", number_of_decimals=2, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=132465, blockseq=1, cardseq=0, ctype="CardIssue")
invalid_card_lwrongamount_simple = DummyATCard(txid="fc48be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0", amount=15000000, donation_txid="3016e6fea3bf9288b61ebbc378530f73351df8be470f37ffa754187d70e9a6e9", number_of_decimals=2, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=132465, blockseq=1, cardseq=0, ctype="CardIssue")

# This bundle uses the correct amount in card 1, but an incorrect one in card 2. This should make both cards invalid.
invalid_card_lwrongamount_bundle1 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=540000, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=1, ctype="CardIssue")
invalid_card_lwrongamount_bundle2 = DummyATCard(txid="59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94", amount=7460001, donation_txid="dcdcb78879fcdfd675c9df8ec839b45c27462adabebf027bbe3807a5f16b80a8", number_of_decimals=2, sender="mvrm2HAoKqiCmeQiwKMuEFpeEn7rJEmpMz", blocknum=132499, blockseq=1, cardseq=1, ctype="CardIssue")

# CardTransfer is completely fabricated.
valid_ctransfer_lx = DummyATCard(txid="0048be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0", amount=15000, donation_txid=None, number_of_decimals=2, sender="mie75nFHrNAHHKfQ141fWfWozdMnaec8mb", blocknum=135000, blockseq=1, cardseq=0, ctype="CardTransfer")


# is_valid_issuance(provider: Provider, card: object, total_issued_amount: int, tracked_address: str, multiplier: int, at_version: int=1, startblock: int=None, endblock: int=None, debug: bool=False)
def test_issuance_valid_unlimited():
    valid = a.is_valid_issuance(provider=provider, card=valid_card_ul, total_issued_amount=5745000, tracked_address=BURNADDR, multiplier=unlimited_deck.multiplier, debug=True)
    assert valid == True

def test_issuance_valid_limited_simple():
    valid = a.is_valid_issuance(provider=provider, card=valid_card_lsimple, total_issued_amount=12000000, tracked_address=BURNADDR, multiplier=limited_deck.multiplier, startblock=limited_deck.startblock, endblock=limited_deck.endblock, debug=True)
    assert valid == True

def test_issuance_valid_limited_bundle():
    valid = a.is_valid_issuance(provider=provider, card=valid_card_lbundle1, total_issued_amount=8000000, tracked_address=BURNADDR, multiplier=limited_deck.multiplier, startblock=limited_deck.startblock, endblock=limited_deck.endblock, debug=True)
    assert valid == True

def test_issuance_invalid_limited_wrongblock():
    valid = a.is_valid_issuance(provider=provider, card=invalid_card_lwrongblock, total_issued_amount=12000000, tracked_address=BURNADDR, multiplier=limited_deck.multiplier, startblock=limited_deck.startblock, endblock=limited_deck.endblock, debug=True)
    assert valid == False

def test_issuance_invalid_limited_wrong_amount_simple():
    valid = a.is_valid_issuance(provider=provider, card=invalid_card_lwrongamount_simple, total_issued_amount=15000000, tracked_address=BURNADDR, multiplier=limited_deck.multiplier, startblock=limited_deck.startblock, endblock=limited_deck.endblock, debug=True)
    assert valid == False

def test_issuance_invalid_limited_wrong_amount_bundle():
    valid = a.is_valid_issuance(provider=provider, card=invalid_card_lwrongamount_bundle1, total_issued_amount=15000000, tracked_address=BURNADDR, multiplier=limited_deck.multiplier, startblock=limited_deck.startblock, endblock=limited_deck.endblock, debug=True)
    assert valid == False


def test_at_parser():
    # The bundle here results in a correct total amount. The only invalid card should be the last one.
    cards = [valid_card_lsimple, valid_card_lbundle1, valid_card_lbundle2, invalid_card_lwrongblock]
    result = a.at_parser(cards, provider, limited_deck, debug=True)
    assert len(result) == 3
    assert result[0].txid == "fc48be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0"
    assert result[-1].txid == "59a127ed9d44578d2644cf300380e473844fc017bbaf1ba62e0337e27f834e94"

def test_at_parser_invalid_bundle():
    # the both latter cards represent a bundle which together issue one unit above the correct amount. Thus only the first one should be valid.
    cards = [valid_card_lsimple, invalid_card_lwrongamount_bundle1, invalid_card_lwrongamount_bundle2]
    result = a.at_parser(cards, provider, limited_deck, debug=True)
    assert len(result) == 1
    assert result[0].txid == "fc48be95925d3c7b96a6b07e76a4a3b9db55cd2110bccf5375497099b1bf68b0"
