import pytest
import pypeerassets.at.extension_protocol as ep
import pypeerassets.at.constants as c

from pypeerassets.networks import SlimcoinTestnet
from pypeerassets.protocol import Deck, CardTransfer, IssueMode

# TODO: DT decks still not covered until after Beta 1.

DECK_UNPARSED_AT1 = Deck(name="TestDeckAT1",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            asset_specific_data=b'\x10\x02@dJ\x14@\xf1c\xa4\xd0\xa8\xbcD\xb4\xba\x00\xb9T\xc2\xbd\xbe\xfb\x87|\xf4P\x02') # same as "official" Testnet PoB token
DECK_UNPARSED_AT2 = Deck(name="TestDeckAT2",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            asset_specific_data=b'\x10\x02@dJ\x14?\xd2\xeb\xbe7\x9a\xe3\xd0\xa7\xdd\xf7\x14\xb4\x9c\xebi\xd7\x90q\xa1P\x02X\x90\xa1\x0f`d') # same as ATTokenNotPoB
DECK_UNPARSED_INV = Deck(name="TestDeckATInvalid",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            asset_specific_data=b'\x02@dJ\x14?\xd2\xeb\xbe7\x9a\xe3\xd0\xa7\xdd\xf7\x14\xb4\x9c\xebi\xd7\x90q\xa1P\x02X\x90\xa1\x0f`d') # incorrect asset_specific_data string
DECK_PARSED_AT1 = Deck(name="TestDeckAT3",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            multiplier=1000,
            at_type=2,
            at_address="mxzBmhiUyLAEYXYrtzZm139f6wY9nN4FWM",
            addr_type=2,
            startblock=100000,
            endblock=200000,
            extradata="1a1a1a")
DECK_PARSED_AT2 = Deck(name="TestDeckAT4",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            multiplier=999999,
            at_type=2,
            at_address="mxzBmhiUyLAEYXYrtzZm139f6wY9nN4FWM",
            addr_type=2)
DECK_PARSED_INV = Deck(name="TestDeckATInvalid2",
            number_of_decimals=2,
            issue_mode=IssueMode.CUSTOM.value,
            network="tslm",
            production=True,
            version=1,
            multiplier=99999999990000000000, # multiplier overflow
            at_type=2,
            at_address="mxzBmhiUyLAEYXYrtzZm139f6wY9nN4FWM",
            addr_type=2)


# card data 1 are derived from testnet tx 0b456e4fd48ef9c75c824042752a643be06c60aa1e858e12c8392539f19fa9cf with donation txid f956f090448a705723bdc22434bb5aa8ef6b27d18a0d5e458869ca7df0e1d4f8
CARD1 = CardTransfer(deck=DECK_UNPARSED_AT1,
                     receiver=["mpbGv4wmNste2VpznteMKncrBoDRw1YMkf"],
                     amount=[2000000],
                     version=1,
                     asset_specific_data=b"\n \xf9V\xf0\x90D\x8apW#\xbd\xc2$4\xbbZ\xa8\xefk'\xd1\x8a\r^E\x88i\xca}\xf0\xe1\xd4\xf8")

# card data 2 is derived from textnet tx cb20b32ec8791a5bc7deba9b6a29d0fff86860e47474b7cb49cb58df0279a81c with donation txid 3016e6fea3bf9288b61ebbc378530f73351df8be470f37ffa754187d70e9a6e9
CARD2 = CardTransfer(deck=DECK_UNPARSED_AT1,
                     receiver=["mwFgapYPcSmfbeKcecB9Hy4vsLEFoAy25g"],
                     amount=[2000],
                     version=1,
                     asset_specific_data=b'0\x16\xe6\xfe\xa3\xbf\x92\x88\xb6\x1e\xbb\xc3xS\x0fs5\x1d\xf8\xbeG\x0f7\xff\xa7T\x18}p\xe9\xa6\xe9')
CARD3 = CardTransfer(deck=DECK_UNPARSED_AT1,
                     receiver=["msN5EUgocdFaAie9PsqKh8bJJ79shRnL91"],
                     amount=[5000],
                     version=1,
                     asset_specific_data=b'')

@pytest.mark.parametrize(("deck", "ataddr", "multiplier", "startblock"),
                         [(DECK_UNPARSED_AT1, "mmSLiMCoinTestnetBurnAddress1XU5fu", 100, None),
                          (DECK_UNPARSED_AT2, "mmLRYBJMsLBrHCGQAwx4fwMt3egt1J3qbo", 100, 100),
                          (DECK_PARSED_AT1, "mxzBmhiUyLAEYXYrtzZm139f6wY9nN4FWM", 1000, 100000),
                          (DECK_PARSED_AT2, "mxzBmhiUyLAEYXYrtzZm139f6wY9nN4FWM", 999999, None)])
def test_initialize_custom_deck_attributes(deck, ataddr, multiplier, startblock):
    # ep.initialize_custom_deck_attributes(deck, "tslm") is not necessary, will be called by Deck.__init__()
    assert deck.at_address == ataddr
    assert deck.multiplier == multiplier
    assert deck.startblock == startblock


@pytest.mark.parametrize(("deck", "exception"),
                         [(DECK_UNPARSED_INV, AssertionError),
                          (DECK_PARSED_INV, AssertionError)])
def test_initialize_custom_deck_attributes_invalid(deck, exception):
    with pytest.raises(exception):
        assert "at_address" in deck.__dict__.keys()


@pytest.mark.parametrize(("card", "ctype", "dtxpresent", "dtxid"),
                          [(CARD1, "CardIssue", True, "f956f090448a705723bdc22434bb5aa8ef6b27d18a0d5e458869ca7df0e1d4f8"),
                           (CARD2, "CardTransfer", False, None),
                           (CARD3, "CardTransfer", False, None)])
def test_initialize_custom_card_attributes(card, ctype, dtxpresent, dtxid):
    # ep.initialize_custom_card_attributes(card, DECK_UNPARSED_AT1)
    assert card.type == ctype
    assert ("donation_txid" in card.__dict__.keys()) == dtxpresent
    if dtxpresent:
        assert card.donation_txid == dtxid
        assert card.at_type == 2 # only CardIssues have the card.at_type set

@pytest.mark.parametrize(("datadict", "result"),
                         [({"hash" : b'@\xf1c\xa4\xd0\xa8\xbcD\xb4\xba\x00\xb9T\xc2\xbd\xbe\xfb\x87|\xf4', "hash_type" : 2}, "mmSLiMCoinTestnetBurnAddress1XU5fu"),
                          ({"hash" : b'\x0eS\xff{\xcc\x18\x12F<\xf4\x81\x85\xf3<\xf8\xce\x1d\xe7#\xcb', "hash_type" : 2}, "mgpiP2Dc5QweKFS55HvRqsWyQ6PMXJCVCk")])
def test_get_at_address(datadict, result):
    at_address = ep.get_at_address(datadict, SlimcoinTestnet)
    assert type(at_address) == str
    assert at_address == result

@pytest.mark.parametrize(("invaliddict", "exception"),
                         [({"hash" : b'@\xf1c\xa4\xd0\xa8\xbcD\xb4\xba\x00\xb9T\xc2\xbd\xbe\xfb\x87|\xf4', "hash_type" : "1"}, TypeError),
                          ({"hash" : b"", "hash_type" : 3}, ValueError),
                          ({"hash" : "ABCD", "hash_type" : 2 }, TypeError)])
def test_get_at_address_invalid(invaliddict, exception):
    with pytest.raises(exception):
        at_address = ep.get_at_address(invaliddict, SlimcoinTestnet)

def test_looks_like_at_cardissue():
    datadict = {"txid" : bytes.fromhex("d59dec02c885ef98c71df5a4ef8f4e644b1dfee9303fe9af35b8c5ebdcbae2dc"), "vout" : 1}
    valid = ep.looks_like_at_cardissue(datadict)
    assert valid == True

@pytest.mark.parametrize("invaliddict", [{"txid" : "ABCD", "vout" : "1"},
                                         {"txid" : bytes.fromhex("d59dec02c885ef98c71df5a4ef8f4e644b1dfee9303fe9af35b8c5ebdcbae2dc25")},
                                         {"txid" : bytes.fromhex("d59dec02c885ef98c71df5a4ef8f4e644b1dfee9303fe9af35b8c5ebdcbae2dc"), "vout" : "A" }])
def test_looks_like_at_cardissue_invalid(invaliddict):
    valid = ep.looks_like_at_cardissue(invaliddict)
    assert valid == False

# def is_valid_address(address: str, hash_type: int, network: namedtuple) -> bool: # (P2PKH address verification, should also work with P2SH)
def test_looks_like_valid_address():
    address = "mktjZm8J8LQ9S7fn3pBba3sTNicCujDAFS"
    valid = ep.looks_like_valid_address(address, 2, SlimcoinTestnet)
    assert valid == True

# tests: invalid first letter, too short, too long.
@pytest.mark.parametrize("address", ["zktjZm8J8LQ9S7fn3pBba3sTNicCujDAFF", "mktjZm8J8LQ9S7fn3pBba3sNi", "mktjZm8J8LQ9S7fn3pBba3sTNicCujDAFF4lzaK5dAsSf"])
def test_looks_like_valid_address_invalid(address):
    valid = ep.looks_like_valid_address(address, 2, SlimcoinTestnet)
    assert valid == False
