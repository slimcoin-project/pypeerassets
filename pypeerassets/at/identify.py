### VERSION 2 with new formats ###


"""This script bundles the functions to identify Addresstrack transactions (above all CardIssues) without needing a Provider, so it can be called from protocol.CardTransfer.__init__ without having to integrate new variables into CardTransfer.
It only allows a very basic identification of CardIssues and DeckIssues, but that is enough because anyway bogus transactions could be inserted until the parser is called.
Also these functions are all very light so they don't compromise resource usage. The heavy part is in at_parser.py.

This prototype uses the following metadata items to identify addresstrack transactions:
- deck.asset_specific_data(TRK_IDENTIFIER:ADDRESS:MULTIPLIER)
- card.asset_specific_data(TX_IDENTIFIER:TXID:VOUT)
(question: cannot TX_IDENTIFIER be changed to TRK_IDENTIFIER? Problem may be extensibility ...)

### Comments 08/20:
- to get rid of the colons (which occupy a whole byte each!) it may be useful to first use those with a fixed length, and specify everything in at_transaction_formats.
- thus it would be better the following:
- Deck data for AT: 2 bytes as AT identifier, Multiplier (2 bytes, up to 65535), Address (rest).
- Deck data for DT: 2 bytes as DT identifier, Multiplier (2 bytes), length of distribution period (3 bytes, up to ~16 million), tokens per distribution period (2 bytes, up to 65535), Proposer vote threshold (1 byte), Special Distribution periods (1 byte), TXID of deck of SDP token (32 bytes) => 43 bytes
- Card Issue data for AT: 2 byte as AT identifier, TXID (32 bytes), vout (rest)
- Card Issue data for DT: 2 byte as DT identifier, TXID (32 bytes), vout (rest)

###

Perhaps a "COIN" identifier can be useful, if full network agnosticism is wanted. Deck includes a network parameter, but if in the future Decks could be transferred between blockchains, this would be needed.

Use cases:
- trustless ICO distributions
- token as recompensation for donations
- proof-of-burn distribution (if tracked address is unspendable)

TODO: CardBurn! (It's probably not needed to introduce a burn feature but the interferences of existing burn features should be looked at.)

TODO: Should this be integrated in the Deck class? We anyway have added variables.

"""

from pypeerassets.at.transaction_formats import DECK_SPAWN_AT_FORMAT, DECK_SPAWN_DT_FORMAT, CARD_ISSUE_AT_FORMAT, CARD_ISSUE_DT_FORMAT, getfmt

AT_IDENTIFIER = b'AT' # was b'A'[0]
DT_IDENTIFIER = b'DT'
PEERCOIN_BEGINNINGS = ("m", "n", "P", "p")
SLIMCOIN_BEGINNINGS = ("m", "n", "S", "s")
ADDRESS_BEGINNINGS = PEERCOIN_BEGINNINGS # for preliminary tests. This should be replaced with a mechanism which retrieves the "network" parameter.


def is_at_deck(datastring):
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

    except IndexError: # datastring too short
        return False
    return False

def is_at_cardissue(datastring):
    # addresstrack (AT and DT) issuance transactions reference the txid of the donation in "card.asset_specific_data"

    try:
        ident = datastring[:2]

        if ident == AT_IDENTIFIER:
            txid = getfmt(datastring, CARD_ISSUE_AT_FORMAT,"dtx")
        elif ident == DT_IDENTIFIER:
            txid = getfmt(datastring, CARD_ISSUE_DT_FORMAT,"dtx")

    except (IndexError, UnboundLocalError) as e:
        return False

    #print("checking txid", txid)
    if is_valid_txid(txid):
        #print("Is valid txid")
        return True
    return False

def is_valid_address(address):
    # ultra-simplified method to ensure the address format is correct, without rpc node connection
    # could be replaced with a full regex validator as it's not really heavy

    #address = bytes_to_base58(address_bytes) # this would be necessary if we decide to encode the addr in base58!
    #print(address, address[0])
    if address[0] not in ADDRESS_BEGINNINGS:
        return False
    if 26 < len(address) <= 35:
        return True

def is_valid_txid(txid_bytes):
    # tests if txid is 32 bytes (64 hex characters) long. Not doing full validity check for performance reasons,
    # anyway the parser detects bogus issuances.
    # TODO: should be shorter or directly replaced with a simple length check of the byte string.
    try:
        txid = txid_bytes.hex()
        if len(txid) == 64:
            return True
        else:
            return False
    except ValueError:
        return False

