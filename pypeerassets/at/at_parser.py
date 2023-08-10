from pypeerassets.provider import Provider
from decimal import Decimal
from pypeerassets.at.extended_utils import process_cards_by_bundle
import pypeerassets.pautils as pu

"""
Thus module bundles parser functions for AT tokens which use the RPC node/provider.
The algorithm checks all cards in a bundle at once.
It is complemented by extension_protocol.py.

NOTE: It was decided that the credited address is the one in the first input (vin).
"Pooled burning" or "Pooled donation" could be supported later with an OP_RETURN based format,
where "burners" or "donors" explicitly define who gets credited in which proportion.
"""

def is_valid_issuance(provider: Provider,
                      card: object,
                      tracked_address: str,
                      deck_factor: int,
                      total_issued_amount: int,
                      at_version: int=1,
                      startblock: int=None,
                      endblock: int=None,
                      debug: bool=False) -> bool:

    try:
        checked_tx = check_donation(provider, card.donation_txid, tracked_address, deck_factor, total_issued_amount=total_issued_amount, startblock=startblock, endblock=endblock)
        assert card.sender == pu.find_tx_sender(provider, checked_tx)

    except ValueError as ve:
        if debug:
            print("Invalid transaction:", ve)
        return False

    except AssertionError:
        if debug:
            print("Error: Card sender {} not entitled to issue these cards (correct transaction sender: {}).".format(card.sender, tx_sender))
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

    deck_factor = deck.multiplier * (10 ** deck.number_of_decimals)

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
                if is_valid_issuance(provider, card, deck.at_address,
                                     deck_factor, issued_amount,
                                     startblock=deck.startblock,
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

def check_donation(provider: object,
                   txid: str,
                   tracked_address: str,
                   deck_factor: int=None,
                   total_issued_amount: int=None,
                   startblock: int=None,
                   endblock: int=None,
                   debug: bool=False):

    # bundles all checks to the donation/burn transaction itself,
    # if valid, returns the raw transaction as json.
    # if not, raises error
    # total_issued_amount is optional, as some functions don't require the amount check.

    # check 1: txid must be valid and confirmed
    try:
        tx = provider.getrawtransaction(txid, 1)
        # if we assert only tx exists then error messages "fall through" as they're also in JSON format.
        # assert tx.get("txid") is not None
        tx_blockhash = tx["blockhash"]
    except KeyError:
        raise ValueError("Transaction is not confirmed.")
    except Exception as e:  # bad txid or bad provider
        raise ValueError("Bad txid or wrongly formatted provider.")

    # check 2: amount transferred to the tracked_address must be equal to expected amount

    total_tx_amount = Decimal(0)
    for vout in tx["vout"]:
        try:
            if vout["scriptPubKey"]["addresses"][0] == tracked_address:
                if vout["value"] > 0:
                    total_tx_amount += Decimal(vout["value"])
        except KeyError:
            continue
    if debug:
        print("Total donated/burnt amount:", total_tx_amount)

    if total_issued_amount:
        if (total_tx_amount * deck_factor) != total_issued_amount:
            raise ValueError("Donation value {} not matching expected amount {}.".format(total_tx_amount, total_issued_amount))
    else:
        if total_tx_amount == 0:
            raise ValueError("Donation not spending nothing to the tracked address.")

    if endblock or startblock:
        # TODO: using the 'time' variable may be faster, as you only have to lookup the start/end blocks.
        tx_height = provider.getblock(tx_blockhash)["height"]

        if endblock and (tx_height > endblock):
            raise ValueError("Issuance at block {}, after deadline {}.".format(tx_height, endblock))

        if startblock and (tx_height < startblock):
            raise ValueError("Error: Issuance at block {}, before deadline {}.".format(tx_height, startblock))

    return tx

