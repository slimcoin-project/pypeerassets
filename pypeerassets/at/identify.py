from pypeerassets.at.transaction_formats import DECK_SPAWN_AT_FORMAT, DECK_SPAWN_DT_FORMAT, CARD_ISSUE_AT_FORMAT, CARD_ISSUE_DT_FORMAT, getfmt

"""This script bundles the functions to identify Address-Tracker transactions (above all CardIssues) without needing a Provider, so it can be called from protocol.py without having to integrate new attributes to CardTransfer.
It only allows a very basic identification of CardIssues and DeckIssues, but that is enough because anyway bogus transactions could be inserted until the parser is called.
Also these functions are all very light so they don't compromise resource usage. The heavy part is in at_parser.py/dt_parser.py.


### Future possible improvements ###

* CardBurn could be introduced for DT tokens, although it currently is not urgent.
* Structure-wise this file could be integrated in the Deck class.

"""

AT_IDENTIFIER = b'AT' # was b'A'[0]
DT_IDENTIFIER = b'DT'
PEERCOIN_BEGINNINGS = ("m", "n", "P", "p")
SLIMCOIN_BEGINNINGS = ("m", "n", "S", "s")
ADDRESS_BEGINNINGS = PEERCOIN_BEGINNINGS # for preliminary tests. This should be replaced with a mechanism which retrieves the "network" parameter.

def is_at_deck(datastring: bytes) -> bool:
    # this needs the identification as addresstrack deck.
    try:

        ident = datastring[:2] # always first 2 bytes, either AT or DT

        if ident == AT_IDENTIFIER:
            address = getfmt(datastring, DECK_SPAWN_AT_FORMAT, "adr")
            address = address.decode("utf-8") # this can be perhaps made without decoding, as full validation isn't needed.

            if is_valid_address(address):
                return True

        elif ident == DT_IDENTIFIER:
            if len(datastring) >= DECK_SPAWN_DT_FORMAT["sdq"][0]: # last mandatory item
                return True

    except (IndexError, TypeError): # datastring not existing or too short
        return False
    return False

def is_at_cardissue(datastring: bytes) -> bool:
    # addresstrack (AT and DT) issuance transactions reference the txid of the donation in "card.asset_specific_data"

    try:

        ident = datastring[:2]

        if ident == AT_IDENTIFIER:
            fmt = CARD_ISSUE_AT_FORMAT
        elif ident == DT_IDENTIFIER:
            fmt = CARD_ISSUE_DT_FORMAT

        txid = getfmt(datastring, fmt, "dtx")

        assert len(getfmt(datastring, fmt, "out")) > 0
        assert len(txid) == 32

    except (IndexError, UnboundLocalError, TypeError, AssertionError) as e:
        return False

    return True

def is_valid_address(address: str) -> bool:
    # ultra-simplified method to ensure the address format is correct, without rpc node connection
    # could be replaced with a full regex validator as it's not really heavy
    # TODO: this only works with base58, not with bech32 addresses.
    # TODO: when reworking for bech32 also integrate Slimcoin address check (now its only Peercoin).
    # This can only be solved when the bech32 prefix is known (slm?)

    #address = bytes_to_base58(address_bytes) # this would be necessary if we decide to encode the addr in base58!
    try:
        assert address[0] in ADDRESS_BEGINNINGS
        assert 26 < len(address) <= 35
    except AssertionError:
        return False
    return True
