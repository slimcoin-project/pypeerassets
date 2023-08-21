# idea to develop further: the original classes could provide an extension_data attribute with type dict.
# first field is the extension name (i.e. "AT")
# second field is another dict of the current attributes.
# MODIF: "identify" integrated here.

import pypeerassets.at.constants as c
from pypeerassets.at.protobuf_utils import parse_protobuf
from pypeerassets.networks import net_query
from pypeerassets.hash_encoding import HASHTYPE, hash_to_address
from collections import namedtuple

def initialize_custom_deck_attributes(deck, network, epoch_length=None, epoch_reward=None, min_vote=None, sdp_periods=None, sdp_deck=None, multiplier=None, at_address=None, debug=False):
    ### additional Deck attributes for AT/DT types


    try:
        data = parse_protobuf(deck.asset_specific_data, "deck")

        if data["id"] == c.ID_AT:

            deck.at_address = get_at_address(data, net_query(network))
            deck.multiplier = multiplier if multiplier else data["multiplier"]
            deck.addr_type = data["hash_type"] ### new. needed for hash_encoding.

            # optional attributes
            deck.startblock = data.get("startblock")
            deck.endblock = data.get("endblock")
        else:
            assert data["id"] == c.ID_DT
            deck.epoch_length = epoch_length if epoch_length else data["epoch_len"]
            deck.standard_round_unit = deck.epoch_length // c.DT_ROUND_DIVISION # value of this constant: 28
            deck.epoch_reward = epoch_reward if epoch_reward else data["reward"] # shouldn't this better be called "epoch_reward" ?? # TODO

            # optional attributes
            deck.min_vote = min_vote if min_vote else data.get("min_vote")
            deck.sdp_periods = sdp_periods if sdp_periods else data.get("special_periods")

            try:
                deck.sdp_deckid = sdp_deck.hex() if sdp_deck else data.get("voting_token_deckid").hex()
            except AttributeError:
                deck.sdp_deckid = None
        deck.at_type = data["id"]

    except (ValueError, KeyError):
        if debug:
            print("Non-Standard asset-specific data. Not adding special parameters.")
    except AssertionError:
        if debug:
            print("No valid AT/DT deck.")


def initialize_custom_card_attributes(card, deck, donation_txid=None):
    ### AT ###
    # if deck contains correct addresstrack-specific metadata and the card references a txid,
    # the card type is CardIssue. Will be validated later by custom parser.
    # modified order because with AT tokens, deck issuer can be the receiver.
    # CardBurn is not implemented in AT, because the deck issuer should be
    # able to participate normally in the transfer process. Cards can however
    # be burnt sending them to unspendable addresses.

    try:
        assert "at_type" in deck.__dict__ and deck.at_type in (c.ID_AT, c.ID_DT)

        try:
            card.extended_data = parse_protobuf(card.asset_specific_data, "card")
            assert is_at_cardissue(card.extended_data) == True
            card.type = "CardIssue"
            card.donation_txid = donation_txid if donation_txid else card.extended_data["txid"].hex()
        except (TypeError, AssertionError):
            # TypeError is risen when the protobuf value is None
            card.type = "CardTransfer"

        card.at_type = deck.at_type # # MODIF: replaces the obsolete card.extended_data.id
    except (ValueError, KeyError, AssertionError):
        # this happens with non-dt tokens using a custom parser,
        # or with faulty dt tokens with data not protobuf formatted, or one of the txid and vout values missing.
        # This doesn't raise an error, because if a non-compatible asset_specific_data in deck
        # by chance gets interpreted as AT or DT, it should not be necessarily be invalid.
        card.type = "CardTransfer"

def get_at_address(data: dict, network: namedtuple) -> bool: ### changed from datastring to data, bytes to object. Added network param.
    # this needs the identification as addresstrack deck.
    # before this was: is_at_deck
    # try:

        # ident = data["id"]

        #if ident == AT_ID:
    try:
        address = hash_to_address(data["hash"], data["hash_type"], network)
    except NotImplementedError:
        raise ValueError("Hash type not implemented.") # util not implemented we can't process these hashes.
    except KeyError:
        raise ValueError("Necessary items not found.")

    try:
        assert is_valid_address(address, data["hash_type"], network)
        return address

        # data.update({"at_address" : address })
        # return True

        #elif ident == DT_ID:
        #    return True

    except AssertionError: # datastring not existing or too short
        raise ValueError("Invalid address.")
    # return False

def is_at_cardissue(data: dict) -> bool:
    # addresstrack (AT and DT) issuance transactions reference the txid of the donation in "card.asset_specific_data"

    # WORKAROUND. vout is not saved in protobuf if it's 0.
    #if "vout" not in data:
    #    data.update({ "vout": 0 })
    try:
        assert len(data["txid"]) == 32
        # assert data["vout"] is not None

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
