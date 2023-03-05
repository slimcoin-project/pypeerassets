# from pypeerassets.at.transaction_formats import DECK_SPAWN_AT_FORMAT, DECK_SPAWN_DT_FORMAT, CARD_ISSUE_AT_FORMAT, CARD_ISSUE_DT_FORMAT, getfmt
from pypeerassets.hash_encoding import HASHTYPE, hash_to_address
from collections import namedtuple
from pypeerassets.networks import net_query
## changed to protobuf.
## changed to neutral address format. The previous one would not have worked with SLM mainnet.

"""This script bundles the functions to identify Address-Tracker transactions (above all CardIssues) without needing a Provider, so it can be called from protocol.py without having to integrate new attributes to CardTransfer.
It only allows a very basic identification of CardIssues and DeckIssues, but that is enough because anyway bogus transactions could be inserted until the parser is called.
Also these functions are all very light so they don't compromise resource usage. The heavy part is in at_parser.py/dt_parser.py.


### Future possible improvements ###

* The mechanism and the Deck/CardTransfer parts around them should be reworked as part of the Extensions structure.

"""

AT_IDENTIFIER = b'AT'
DT_IDENTIFIER = b'DT'

def is_at_deck(data: dict, network: namedtuple) -> bool: ### changed from datastring to data, bytes to object. Added network param.
    # this needs the identification as addresstrack deck.
    try:

        ident = data["id"]

        if ident == AT_IDENTIFIER:
            try:
                address = hash_to_address(data["hash"], data["hash_type"], network)
            except NotImplementedError:
                return False # util not implemented we can't process these hashes.

            if is_valid_address(address, data["hash_type"], network):
                data.update({"at_address" : address }) # OPTIMIZATION. Not elegant but saves a hash operation. check for side effects!
                return True

        elif ident == DT_IDENTIFIER:
            return True

    except (IndexError, TypeError, KeyError): # datastring not existing or too short
        return False
    return False

def is_at_cardissue(data: dict) -> bool:
    # addresstrack (AT and DT) issuance transactions reference the txid of the donation in "card.asset_specific_data"

    # WORKAROUND. vout is not saved in protobuf if it's 0.
    if "vout" not in data:
        data.update({ "vout": 0 })
    try:
        assert len(data["txid"]) == 32
        assert data["vout"] is not None

    except (UnboundLocalError, AssertionError): # with protobuf we don't need IndexError, TypeError "as e" not needed here?
        return False

    return True

def is_valid_address(address: str, hash_type: int, network: namedtuple) -> bool:
    # ultra-simplified method to ensure the address format is correct, without rpc node connection
    # could be replaced with a full regex validator as it's not really heavy

    try:
        b58pref = network.base58_prefixes
        if hash_type in (2, 3): # p2pkh & p2sh => p2pk too?
            address_prefixes = [ key for key in b58pref.keys() if b58pref.get(key) == HASHTYPE[hash_type] ]
            assert address[0] in address_prefixes
            assert 26 < len(address) <= 35
        else:
            # p2pk & segwit / taproot addresses currently not implemented.
            # at this moment, DT and AT support only base58.
            raise NotImplementedError
    except AssertionError:
        return False
    return True
