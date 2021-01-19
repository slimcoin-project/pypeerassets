import pytest
import pypeerassets.at.identify as idt
from pypeerassets.provider import Provider, RpcNode
from pypeerassets.networks import PeercoinTestnet

# Deck spawn datastrings (asset_specific_data)
AT_DECK_DATASTR = b"AT02mrBvQCAq3YPVQeq56kvAtjuD82B9hxNFdL" # > beginning with AT, 4 bytes + valid address
DT_DECK_DATASTR = b"DT4I0Fr+48dD" # > 8 bytes, beginning with DT
INC_DECK_DATASTR1 = b"890890sdjklsjdkldfjklAdsjfRDFEu0" # not beginning with AT or DT
INC_DECK_DATASTR2 = b"ATdkl{wejklUfwupDFUYUr0oI1djklf" # no correct address format

# Card issue datastrings (asset_specific_data)
AT_CARD_DATASTR = b"AT\xdbN\xd7\x8c\xb7\x88Te&\xb8\x0c\xfb\xff\xce\xa5\x88\x17\xe0>C*\x85\xdd\xe3\x1b!\xaep\x05\xcd\xd0r1" # > beginning with AT, 2 bytes + txid (32 bytes) + output (1 byte)
DT_CARD_DATASTR = b"DT\xa3\x0c\xc7_\xa4\xbc\x11k6!\xef\x8c\xcb\x11SUI7\x7fS\xc6\xbejN\xdc\xba\x03\x1e\x89\xa6\xfe\xeb1" # > beginning with DT, 2 bytes + txid (32 bytes) + output (1 byte)
INC_CARD_DATASTR1 = b"A0\xa3\x0c\xc7_\xa4\xbc\x11k6!\xef\x8c\xcb\x11SUI7\x7fS\xc6\xbejN\xdc\xba\x03\x1e\x89\xa6\xfe\xeb1"
INC_CARD_DATASTR2 = b"DT\xa3\x0c\xc7_\xa4\xbc\x11k6!\xef\x8c\xcb\x11SUI7\x7fS\xc6\xbejN\xdc\xba\x03\x1e\x89\xa6\xfe1"

# Addresses
# TODO: Addresses are currently only for PPC Testnet (hardcoded).
CORR_ADDR1 = "mrBvQCAq3YPVQeq56kvAtjuD82B9hxNFdL"
CORR_ADDR2 = "n33MWUZPUQLNwdeYkVQFNY8ntQcp7t6un8"
INC_ADDR = "mrBvQCAq3YPVQeq56kvAtjuD82B9hxNFdL"

@pytest.mark.parametrize("datastr", [AT_DECK_DATASTR, DT_DECK_DATASTR, INC_DECK_DATASTR1, INC_DECK_DATASTR2])
def test_is_at_deck(datastr):
    result = idt.is_at_deck(datastr)
    if datastr in (AT_DECK_DATASTR, DT_DECK_DATASTR):
        assert result == True
    else:
        assert result == False

@pytest.mark.parametrize("datastr", [AT_CARD_DATASTR, DT_CARD_DATASTR, INC_CARD_DATASTR1, INC_CARD_DATASTR2])
def test_is_at_cardissue(datastr):
    result = idt.is_at_cardissue(datastr)
    if datastr in (AT_CARD_DATASTR, DT_CARD_DATASTR):
        assert result == True
    else:
        assert result == False


@pytest.mark.parametrize("addr", [CORR_ADDR1, CORR_ADDR2, INC_ADDR])
def test_is_valid_address(addr): 
    result = idt.is_valid_address(addr)
    if addr in (CORR_ADDR1, CORR_ADDR2):
        assert result == True
    else:
        assert result == False


def test_is_valid_txid():
    txid = "8c6f859b23be0740c888d22c2c8964e70922a9d519aa6ddc7e081141b6885bb0"
    txid_bytes = bytes.fromhex(txid) 
    result = idt.is_valid_txid(txid_bytes)
    assert result == True
