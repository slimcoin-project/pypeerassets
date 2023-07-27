from pypeerassets.provider import Provider
from decimal import Decimal
from pypeerassets.at.extended_utils import process_cards_by_bundle

"""
Thus module bundles the specific AT parser functions using the RPC node/provider. It is complemented by extension_protocol.py.
"""

# NOTE: It was decided that the credited address is the one in the first vin.
# "Pooled burning" or "Pooled donation" could be supported later with an OP_RETURN based format,
# where "burners" or "donors" explicitly define who gets credited in which proportion.
# NOTE 2: The algorithm checks all cards in a bundle at once.


def is_valid_issuance(provider: Provider, card: object, total_issued_amount: int, tracked_address: str, multiplier: int, at_version: int=1, startblock: int=None, endblock: int=None, debug: bool=False) -> bool:

    # check 1: txid must be valid
    try:
        tx = provider.getrawtransaction(card.donation_txid, 1)
    except Exception:  # bad txid
        if debug:
            print("Error: Bad or non-existing txid.")
        return False

    # check 2: amount transferred to the tracked_address must be equal to issued amount * multiplier
    total_tx_amount = Decimal(0)
    for vout in tx["vout"]:
        try:
            if vout["scriptPubKey"]["addresses"][0] == tracked_address:
                if vout["value"] > 0:
                    total_tx_amount += Decimal(vout["value"])
        except KeyError:
            continue
    if debug:
        print("Total donated/burnt amount:", total_tx_amount, "Multiplier:", multiplier, "Number of decimals:", card.number_of_decimals)
    total_units = int(total_tx_amount * multiplier * (10 ** card.number_of_decimals))

    if total_units != total_issued_amount:
        if debug:
            print("Error: Issuance value too high:", total_tx_amount, "*", multiplier, "* 10 ^", card.number_of_decimals, "<", total_issued_amount)
        return False

    # check 3 (most expensive, thus last): Sender must be identical with the transaction sender.
    # This checks always vin[0], i.e. the card issuer must sign with the same key than the first input is signed.
    # TODO: try to replace with find_tx_sender.
    tx_vin_tx = provider.getrawtransaction(tx["vin"][0]["txid"], 1)
    tx_vin_vout = tx["vin"][0]["vout"]
    tx_sender = tx_vin_tx["vout"][tx_vin_vout]["scriptPubKey"]["addresses"][0]  # allows a tx based on a previous tx with various vouts.

    if card.sender != tx_sender:
        if debug:
            print("Error: Sender {} not entitled to issue these cards (correct sender {}).".format(card.sender, tx_sender))
        return False

    # check 4 if there are pre-defined deadlines

    if endblock or startblock:
        # TODO: using the 'time' variable may be faster, as you only have to lookup the start/end blocks.
        tx_height = provider.getblock(tx["blockhash"])["height"]

        if endblock and (tx_height > endblock):
            if debug:
                print("Error: Issuance at block {}, after deadline {}.".format(tx_height, endblock))
            return False
        if startblock and (tx_height < startblock):
            if debug:
                print("Error: Issuance at block {}, before deadline {}.".format(tx_height, startblock))
            return False

    return True


def at_parser(cards: list, provider: Provider, deck: object, debug: bool=False):

    if debug:
        print("AT Token Parser started.")

    # necessary for duplicate detection.
    cards.sort(key=lambda x: (x.blocknum, x.blockseq, x.cardseq))

    valid_cards = []
    valid_bundles = []
    used_issuance_tuples = []  # this list joins all issuances of sender, txid, vout, to filter out duplicates:

    if debug:
        print("All cards:\n", [(card.blocknum, card.blockseq, card.txid) for card in cards])

    # first, separate CardIssues from other cards
    # card.amount is a list, the sum must be equal to the amount of the tx * multiplier}
    for (card, bundle_amount) in process_cards_by_bundle(cards, debug=debug):
        if card.type == "CardIssue":

            if debug:
                print("Checking issuance: txid {}, sender {}, receiver {}.".format(card.txid, card.sender, card.receiver))

            # check 1: filter out bundle parts and duplicates (less expensive, so done first)
            if card.txid in valid_bundles:
                valid_cards.append(card)
                if debug:
                    print("AT CardIssue: Valid part of an already processed CardBundle. Issued {} token units.".format(card.amount[0]))

            elif (card.sender, card.donation_txid) in used_issuance_tuples:
                if debug:
                    print("Ignoring CardIssue: Duplicate.")

            else:
                issued_amount = bundle_amount if bundle_amount is not None else card.amount[0]
                # if a card has more than one receiver, the cards_postprocess function divides it in several cards.
                # so to check validity of the issuance amount we need to take the whole bundle into account.

                # we need to know how many cards will be processed together,
                # thus also last cindex of the bundle cards is returned.
                # check 2: check if tx exists, sender is correct and amount corresponds to amount in tx (expensive!)
                if is_valid_issuance(provider, card, issued_amount, tracked_address=deck.at_address,
                                     multiplier=deck.multiplier, startblock=deck.startblock,
                                     endblock=deck.endblock, debug=debug):

                    valid_cards.append(card)
                    if bundle_amount is not None:
                        valid_bundles.append(card.txid)
                    used_issuance_tuples.append((card.sender, card.donation_txid))
                    if debug:
                        print("Valid AT CardIssue: {}. Issued {} token units.".format(card.txid, card.amount[0]))
                else:
                    if debug:
                        print("Ignoring CardIssue: Invalid issuance.")
        else:
            if debug:
                print("AT {} {}".format(card.type, card.txid))
            valid_cards.append(card)

    return valid_cards
