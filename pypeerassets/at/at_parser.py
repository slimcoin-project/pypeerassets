from pypeerassets.provider import Provider
from decimal import Decimal
from pypeerassets.at.extended_utils import get_issuance_bundle

"""
Thus module bundles all "heavy" functions for the parser which include the use of the RPC node/provider. It is complemented by extension_protocol.py.
"""


# NOTE: It was decided that the credited address is the one in the first vin. The vin_check thus is obsolete.
# "Pooled burning" or "Pooled donation" could be supported later with an OP_RETURN based format, where
# the "burners" or "donors" explicitly define who gets credited in which proportion.
# MODIFIED: we look now at all cards in a bundle at once.

def is_valid_issuance(provider: Provider, card: object, total_issued_amount: int, tracked_address: str, multiplier: int, at_version: int=1, startblock: int=None, endblock: int=None, debug: bool=False) -> bool:

    # check 1: txid must be valid
    try:
        tx = provider.getrawtransaction(card.donation_txid, 1)
    except: # bad txid
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
            continue # should normally not occur, only perhaps with very exotic scripts.
    if debug:
        print("Total donated/burnt amount:", total_tx_amount, "Multiplier:", multiplier, "Number of decimals:", card.number_of_decimals)
    total_units = int(total_tx_amount * multiplier * (10 ** card.number_of_decimals))

    if total_units != total_issued_amount:
        if debug:
            print("Error: Issuance value too high:", total_tx_amount, "*", multiplier, "* 10 ^", card.number_of_decimals, "<", total_issued_amount)
        return False

    # check 3 (most expensive, thus last): Sender must be identical with the transaction sender.
    # This checks always vin[0], i.e. the card issuer must sign with the same key than the first input is signed.
    tx_vin_tx = provider.getrawtransaction(tx["vin"][0]["txid"], 1)
    tx_vin_vout = tx["vin"][0]["vout"]
    tx_sender = tx_vin_tx["vout"][tx_vin_vout]["scriptPubKey"]["addresses"][0] # allows a tx based on a previous tx with various vouts.

    if card.sender != tx_sender:
        if debug:
            print("Error: Sender {} not entitled to issue these cards (correct sender {}).".format(card.sender, tx_sender))
        return False

    # check 4 if there are deadlines (MODIF 26/3):

    if endblock or startblock:
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


def at_parser(cards: list, provider: Provider, deck: object, debug: bool=True):
    # this should be faster than the first version.

    if debug:
        print("AT Token Parser started.")
    # however, it uses the used_issuance_tuples list, which may grow and lead to memory problems
    ### it may be possible to categorize used_issuance_tuples by sender? But that would lead to additional overhead.
    # if the token is used very much.

    # MODIF: necessary for duplicate detection.
    cards.sort(key=lambda x: (x.blocknum, x.blockseq, x.cardseq))

    valid_cards = []
    issuance_attempts = []
    used_issuance_tuples = [] # this list joins all issuances of sender, txid, vout, to filter out duplicates:

    # first, separate CardIssues from other cards
    # card.amount is a list, the sum must be equal to the amount of the tx * multiplier}
    if debug:
        print("All cards:\n", [(card.blocknum, card.blockseq, card.txid) for card in cards])

    # for card in cards:
    for cindex, card in enumerate(cards):
        if card.type == "CardIssue":
            if debug:
                print("Checking issuance at position {}, txid {}, sender {}, receiver {}.".format(cindex, card.txid, card.sender, card.receiver))
                # print("Deck metadata:", deck)

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, card.donation_txid) not in used_issuance_tuples:

                # if there is more than one receiver, the cards_postprocess function divides it in several cards.
                # so to check validity of the issuance amount we need to take the whole bundle into account.

                # we need to know how many cards will be processed together,
                # thus also last cindex of the bundle cards is returned.
                total_issued_amount, last_bundle_cindex = get_issuance_bundle(cards, cindex)
                if debug and (cindex != last_bundle_cindex):
                    print("Bundle detected from position", cindex, "to position", last_bundle_cindex)
                    print("Total coins issued:", total_issued_amount)
                # check 2: check if tx exists, sender is correct and amount corresponds to amount in tx (expensive!)
                if is_valid_issuance(provider, card, total_issued_amount, tracked_address=deck.at_address,
                                     multiplier=deck.multiplier, startblock=deck.startblock,
                                     endblock=deck.endblock, debug=debug):

                    # valid_cards.append(card)
                    new_valid_cards = cards[cindex:last_bundle_cindex + 1]
                    valid_cards += new_valid_cards
                    used_issuance_tuples.append((card.sender, card.donation_txid))
                    if debug:
                        print("Valid AT CardIssue:", new_valid_cards[0].txid)
                        if len(new_valid_cards) > 1:
                            print("Issuance to", len(new_valid_cards), "receivers.")
                else:
                    if debug:
                        print("Ignoring CardIssue: Invalid issuance.")
            else:
                if debug:
                    print("Ignoring CardIssue: Duplicate or part of already processed CardBundle.")
        else:
            if debug:
                print("AT CardTransfer:", card.txid)
            valid_cards.append(card)

    return valid_cards

def input_addresses(tx, provider): # taken from dt_entities. Should perhaps be an utility in dt_misc_utils.
    addresses = []
    for inp in tx["vin"]:
        try:
            inp_txout = inp["vout"]
            inp_txjson = provider.getrawtransaction(inp["txid"], 1)
        except KeyError: # coinbase transactions
            continue # normally it should be possible to simply return with an empty list here
        addr = inp_txjson["vout"][inp_txout]["scriptPubKey"]["addresses"][0]
        addresses.append(addr)
    return addresses
