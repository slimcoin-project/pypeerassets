from pypeerassets.provider import Provider
from decimal import Decimal

"""
addresstrack_parser.py bundles all "heavy" functions for the parser which include the use of the RPC node/provider. It is complemented by identify.py.

TODO: Ensure: All CardIssues (also those issued by the deck issuer) are invalid if they're not referencing a transaction from the same address correctly. Should be already the case, but incorrect CardIssues by the deck issuer will have to be detected separately. Also "issuances to themselves" must be permitted (See protocol.py).
"""
# new comments:
#NOTE: This first rework is only to change the protocol to Protobuf and the new card.* attributes.
#A second rework could include using btcpy objects like Transaction, TxIn, TxOut ...

# NOTE: It was decided that the credited address is the one in the first vin. The vin_check thus is obsolete.
# "Pooled burning" or "Pooled donation" could be supported later with an OP_RETURN based format, where
# the "burners" or "donors" explicitly define who gets credited in which proportion.

def is_valid_issuance(provider: Provider, card: object, tracked_address: str, multiplier: int, at_version: int=1, startblock: int=None, endblock: int=None, debug: bool=False) -> bool:

    # first we check if there are deadlines (MODIF 26/3):
    if endblock and card.blocknum > endblock:
        return False
    if startblock and card.blocknum < startblock:
        return False

    total_issuance_amount = sum(card.amount) / (10**card.number_of_decimals)

    # check 1: txid must be valid
    try:
        tx = provider.getrawtransaction(card.donation_txid, 1) # MODIF
    except: # bad txid
        if debug:
            print("Error: Bad or non-existing txid.")
        return False

    # check 2: amount transferred to the tracked_address must be equal to issued amount * multiplier
    total_tx_amout = Decimal(0)

    for vout in tx["vout"]:
        try:
            if vout["scriptPubKey"]["addresses"][0] == tracked_address:
                if vout["value"] > 0:
                    total_tx_amount += Decimal(vout["value"])
        except KeyError:
            continue # should normally not occur, only perhaps with very exotic scripts.

    if (total_tx_amount * multiplier) != total_issuance_amount:
        if debug:
            print("Error: Issuance value too high:", tx_amount, "*", multiplier, "<", total_issuance_amount)
        return False

    # check 3 (most expensive, thus last): Sender must be identical with the transaction sender.
    # This checks always vin[0], i.e. the card issuer must sign with the same key than the first input is signed.
    tx_vin_tx = provider.getrawtransaction(tx["vin"][0]["txid"], 1)
    tx_vin_vout = tx["vin"][0]["vout"]
    tx_sender = tx_vin_tx["vout"][tx_vin_vout]["scriptPubKey"]["addresses"][0] # allows a tx based on a previous tx with various vouts.
    if card.sender != tx_sender:
        print("Error: Sender {} not entitled to issue these cards (correct sender {}).".format(card.sender, tx_sender))
        return False
    return True


def at_parser(cards: list, provider: Provider, deck: object, debug: bool=True):
    # this should be faster than the first version.
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
        print("All cards:\n", [(card.blocknum, card.blockpos, card.txid) for card in cards])
    # TODO we might have to sort the cards here.
    for card in cards:
        if card.type == "CardIssue":
            if debug:
                print("checking issuance ...")
                # print("Deck metadata:", deck)

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, card.donation_txid, card.donation_vout) not in used_issuance_tuples:

                # check 2: check if tx exists, sender is correct and amount corresponds to amount in tx (expensive!)
                if is_valid_issuance(provider, card, deck.at_address, deck.multiplier, at_version, deck.startblock, deck.endblock, debug=debug):

                    valid_cards.append(card)
                    used_issuance_tuples.append((card.sender, card.donation_txid, card.donation_vout))
                    if debug:
                        print("AT CardIssue:", card.txid)
                else:
                    if debug:
                        print("Ignoring CardIssue: Invalid data.")
            else:
                if debug:
                    print("Ignoring CardIssue: Duplicate.")
        else:
            # if card.txid != oldtxid: # TODO: this is probably unnecessary, duplicate cards should never exist, only if the deck isn't initialized. The used issuance tuples prevent the rest.
                # oldtxid = card.txid
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


