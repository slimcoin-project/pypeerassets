# this is EXPERIMENTAL!
# part of protocol.py

# idea to develop further: the original classes could provide an extension_data attribute with type dict.
# first field is the extension name (i.e. "AT")
# second field is another dict of the

from pypeerassets.at.constants import AT_ID, DT_ID
from pypeerassets.at.protobuf_utils import parse_protobuf
from pypeerassets.at.identify import is_at_deck, is_at_cardissue
from pypeerassets.networks import net_query

def initialize_custom_deck_attributes(deck, network, epoch_length=None, epoch_quantity=None, min_vote=None, sdp_periods=None, sdp_deck=None, multiplier=None, at_address=None):
    ### additional Deck attributes for AT/DT types: ### PROTOBUF: changed structure a little bit
    # if self.asset_specific_data and self.issue_mode == IssueMode.CUSTOM.value:
        # TODO in Beta 2 this all should go into identify.py

        try:
            data = parse_protobuf(deck.asset_specific_data, "deck")
            if is_at_deck(data, net_query(network)):
                deck.at_type = data["id"]
                if deck.at_type == DT_ID:
                    deck.epoch_length = epoch_length if epoch_length else data["epoch_len"]
                    deck.standard_round_length = (self.epoch_length // 32) * 2 # a round value is better
                    deck.epoch_quantity = epoch_quantity if epoch_quantity else data["reward"] # shouldn't this better be called "epoch_reward" ?? # TODO

                    # optional attributes
                    deck.min_vote = min_vote if min_vote else data.get("min_vote")
                    deck.sdp_periods = sdp_periods if sdp_periods else data.get("special_periods")
                    try:
                        deck.sdp_deckid = sdp_deck.hex() if sdp_deck else data.get("voting_token_deckid").hex()
                    except AttributeError:
                        deck.sdp_deckid = None
                        # print("LEN", self.epoch_length, "REWARD", self.epoch_quantity, "MINVOTE", self.min_vote, "SDPPERIODS", self.sdp_periods, "SDPDECKID", self.sdp_deckid)
                elif deck.at_type == AT_ID:
                    deck.multiplier = multiplier if multiplier else data["multiplier"]
                    deck.at_address = at_address if at_address else data["at_address"] # TODO if possible, improve this!
                    # self.at_address = at_address if at_address else hash_to_address(data["hash"], data["hash_type"], net_query(network)) # TODO: this isn't elegant at all, duplicate hash_to_address with is_at_deck!
                    deck.addr_type = data["hash_type"] ### new. needed for hash_encoding.
        except (ValueError, KeyError):
            # print(self.id)
            print("Non-Standard asset-specific data. Not adding special parameters.")


def initialize_custom_card_attributes(card, deck, donation_txid=None):
    ### AT ###
    # if deck contains correct addresstrack-specific metadata and the card references a txid,
    # the card type is CardIssue. Will be validated later by custom parser.
    # modified order because with AT tokens, deck issuer can be the receiver.
    # CardBurn is not implemented in AT, because the deck issuer should be
    # able to participate normally in the transfer process. Cards can however
    # be burnt sending them to unspendable addresses.


    # MODIF: the is_at_deck check is expensive and thus will not be done here again.
    try:
        assert "at_type" in deck.__dict__ and deck.at_type in (AT_ID, DT_ID)
        card.extended_data = parse_protobuf(card.asset_specific_data, "card")

        if is_at_cardissue(card.extended_data) == True:
            card.type = "CardIssue"

            card.donation_txid = donation_txid if donation_txid else card.extended_data["txid"].hex()
            card.donation_vout = card.extended_data["vout"] # TODO: re-check if this is really optional.
        else:

            card.type = "CardTransfer" # includes, for now, issuance attempts with completely invalid data

        card.at_type = deck.at_type # # MODIF: replaces the obsolete card.extended_data.id
    except (ValueError, KeyError, AssertionError):
        # this happens with non-dt tokens using a custom parser,
        # or with faulty dt tokens with data not protobuf formatted, or one of the txid and vout values missing.
        # This doesn't raise an error, because if a non-compatible asset_specific_data in deck
        # by chance gets interpreted as AT or DT, it should not be necessarily be invalid.
        card.type = "CardTransfer"
