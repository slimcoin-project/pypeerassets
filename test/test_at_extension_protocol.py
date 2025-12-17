import pytest
import pypeerassets.at.extension_protocol as ep

from pypeerassets.networks import SlimcoinTestnet

# use TestObj mockups for these two
# def initialize_custom_deck_attributes(deck, network, epoch_length=None, epoch_reward=None, min_vote=None, sdp_periods=None, sdp_deck=None, multiplier=None, at_address=None, debug=False) -> None:
# this one parses the protobuf from asset_specific_data and initializes deck attributes.

# def initialize_custom_card_attributes(card, deck, donation_txid=None) -> None:
# this one parses the protobuf from asset_specific_data and initializes card attributes.

# def get_at_address(data: dict, network: namedtuple) -> bool:

# def is_at_cardissue(data: dict) -> bool:

# def is_valid_address(address: str, hash_type: int, network: namedtuple) -> bool: # (P2PKH address verification, should also work with P2SH)
def test_is_valid_address():
    address = ""
    valid = ep.is_valid_address(address, 0, SlimcoinTestnet)
    assert valid == True

def test_is_valid_address_invalid():
    address = ""
    valid = ep.is_valid_address(address, 0, SlimcoinTestnet)
    assert valid == False
