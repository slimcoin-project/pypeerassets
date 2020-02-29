"""This script bundles the functions to identify Address-Tracker transactions (above all CardIssues) without needing a Provider, so it can be called from protocol.CardTransfer.__init__ without having to integrate new variables into CardTransfer.
It only allows a very basic identification of CardIssues, but that is enough because anyway bogus transactions could be inserted until the parser is called.
Also these functions are all very light so they don't compromise resource usage. The heavy part is in addresstrack_parser.py.

This prototype uses the following metadata items to identify addresstrack transactions:
- deck.asset_specific_data(TRK_IDENTIFIER:ADDRESS:MULTIPLIER)
- card.asset_specific_data(TX_IDENTIFIER:TXID:VOUT)
(question: cannot TX_IDENTIFIER be changed to TRK_IDENTIFIER? Problem may be extensibility ...)

Perhaps a "COIN" identifier can be useful, if full network agnosticism is wanted. Deck includes a network parameter, but if in the future Decks could be transferred between blockchains, this would be needed.

Use cases:
- trustless ICO distributions
- token as recompensation for donations
- proof-of-burn distribution (if tracked address is unspendable)

TODO: CardBurn! (It's probably not needed to introduce a burn feature but the interferences of existing burn features should be looked at.)

"""

TRK_IDENTIFIER = b'trk'
TX_IDENTIFIER = b'tx'


def is_addresstrack_deck_datastring(datastring):
    # this needs the identification as addresstrack deck.
    # idea: CUSTOM issue mode, in asset_specific_data put: "trk:ADDRESS:MULTIPLIER"
    # question: is an additional marker "COIN" necessary? Probably not, as every deck has a network.

    try:
        assetdata = datastring.split(b':')
        if assetdata[0] == TRK_IDENTIFIER:
            address = assetdata[1].decode("utf-8") # this can be perhaps made without decoding, as full validation isn't needed.
            if is_valid_address(address):
                return True
    except IndexError:
        return False
    return False

def is_addresstrack_issuance_data(data):
    # addresstrack issuance transactions reference the txid of the donation in "card.asset_specific_data"
    # format idea: tx:TXID:vout (maybe "tx" is not necessary, but allows to add other metadata later)
    if data is None:
        return False

    txdata = data.split(b':') # should be always byte, pacli creates str but this seems to be a bug

    if len(txdata) >= 3 and txdata[0] == TX_IDENTIFIER:
        txid = txdata[1].decode("utf-8")

        if is_valid_txid(txid):
            return True
    return False
    

def is_valid_address(address):
    # ultra-simplified method to ensure the address format is correct, without rpc node connection
    # could be replaced with a full regex validator as it's not really heavy

    if address[0] not in ("m", "n", "P", "p"): # Peercoin-specific. Has to be re-coded with network parameters (base58).
        return False
    if 26 < len(address) <= 35:
        return True

def is_valid_txid(txid):
    # tests if txid is an hex number and 64 bytes long. Not doing full validity check for performance reasons,
    # anyway the parser detects bogus issuances.
    if len(txid) == 64:
        try:
            htxid = int(txid, 16)
        except ValueError:
            return False
        return True
