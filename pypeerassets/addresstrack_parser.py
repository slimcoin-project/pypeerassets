"""
addresstrack_parser.py bundles all "heavy" functions for the parser which include the use of the RPC node/provider. It is complemented by addresstrack_identify.py.
"""


def multiplier(card):
    try:
        return int(card.deck_data.split(b":")[3])
    except IndexError:
        return 1 # if no multiplier is set, assume 1 (1 sat = 1 asset unit)

def tracked_address(card): # perhaps change so it takes the data instead of the card?
    address_str = card.deck_data.split(b":")[1].decode("utf-8")
    return address_str # easier as string

def tracked_address_from_deck(deck):
    address_str = deck.asset_specific_data.split(b":")[1].decode("utf-8")
    return address_str

def tracked_transactions(card):
    return card.asset_specific_data.split(":")[1]

def amount_to_address(address, txhash):
    # returns the transaction data from provider: the total amount sent to the specified address inside of the transaction
    pass

def vin_check(tx, address, version):
    if version == 0:
        # v0: Only one vin is permitted
        if len(tx["vin"]) > 1:
            print("Error: More than one input is not permitted in AT V1.")
            return False
    elif version == 1:
        # v1: several vins are permitted, but all from the same address.
        pass
    elif version == 2:
        # v2: several vins are permitted. If there is a change address, biggest vins get fully credited.
        pass

def is_valid_issuance(provider, sender, tracked_address, ref_txid, ref_vout, ref_amountsum, multiplier):
    # for this prototype, only spending transactions where the card issuer is the ONLY sender in the transaction are valid.
    # Transactions must have exactly 1 "vin", coming from the same address.
    # Otherwise, that would lead to more complex and slow (but doable) checks.

    parser_version = 0

    # check 1: txid must be valid
    try:
        tx = provider.getrawtransaction(ref_txid, 1)
    except: # bad txid
        print("Error: Bad txid.")
        return False
    # check 2: amount of the tx to the address must be bigger than issued amount * multiplier
    # This allows issuance of less cards than the "allowed" amount, but then the txid is "used" and can't be used in other issuance. (Could be restricted to the exact amount, discuss.)
    try:
        tx_amount = tx["vout"][ref_vout]["value"]
    except IndexError: # bad vout
        print("Error: Bad vout.")
        return False
    if (tx_amount * multiplier) < ref_amountsum:
        print("Error: Issuance value too high:", tx_amount, "*", multiplier, "<", ref_amountsum)
        return False
    # check 3: tracked address must be correct
    if tx["vout"][ref_vout]["scriptPubKey"]["addresses"][0] != tracked_address:
        print("Error: Incorrect address:", tx["vout"][ref_vout]["scriptPubKey"]["addresses"][0], "correct one:", tracked_address)
        return False
    # check 4: vin rule must correspond to version
    vin_check(tx, sender, parser_version)
    # check 5 (most expensive, thus last): Sender must be identical with the transaction sender.
    tx_vin_tx = provider.getrawtransaction(tx["vin"][0]["txid"], 1)
    tx_vin_vout = tx["vin"][0]["vout"]
    tx_sender = tx_vin_tx["vout"][tx_vin_vout]["scriptPubKey"]["addresses"][0] # allows a tx based on a previous tx with various vouts.
    if sender != tx_sender:
        print("Error: Sender {} not entitled to issue these cards (correct sender {}).".format(sender, tx_sender))
        return False
    return True


def at_parser(cards, provider):

    valid_issuances = []
    issuance_attempts = []
    regular_cards = []
    used_issuance_tuples = [] # this list joins all issuances of sender, txid, vout:
    oldtxid = ""

    # first, separate CardIssues from other cards
    # card.amount is a list, the sum must be equal to the amount of the tx * multiplier

    for card in cards:
        if card.type == "CardIssue":

            txid_b, vout_b = card.asset_specific_data.split(b":")[1:3]
            txid, vout = txid_b.decode("utf-8"), vout_b.decode("utf-8")

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, txid, vout) not in used_issuance_tuples:
                # check 2: check if tx exists, sender is correct and amount corresponds to amount in tx (expensive!)
                ref_amount = sum(card.amount) / (10**card.number_of_decimals)

                if is_valid_issuance(provider, card.sender, tracked_address(card), txid, int(vout), ref_amount, multiplier(card)):
                    valid_issuances.append(card)
                    used_issuance_tuples.append((card.sender, txid, vout))
        else:

            if card.txid != oldtxid:
                oldtxid = card.txid
                regular_cards.append(card)

    return valid_issuances + regular_cards


def update_at_balance(deck, provider, account="", many=999, since=0): ### UNFINISHED ###
    """This function checks if there are new transactions from the addresses from a selected account
       to the tracked address. If yes, it creates the AT transactions with the correct asset_specific_data.
       It may be a challenge to integrate that with pacli?"""

    tracked_address = tracked_address_from_deck(deck)
    tx_list = provider.listtransactions(account, many, since)

