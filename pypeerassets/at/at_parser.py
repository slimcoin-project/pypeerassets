# from pacli.provider import provider # this may be a solution, but isn't elegant as pacli should not be a dependance

"""
addresstrack_parser.py bundles all "heavy" functions for the parser which include the use of the RPC node/provider. It is complemented by addresstrack_identify.py.

TODO: Ensure: All CardIssues (also those issued by the deck issuer) are invalid if they're not referencing a transaction from the same address correctly. Should be already the case, but incorrect CardIssues by the deck issuer will have to be detected separately. Also "issuances to themselves" must be permitted (See protocol.py).

TODO: card.deck isn't possible as deck isn't an attribute of card (why?)
Workaround: deck_data attribute for CardTransfer. Look later for a more elegant method. 
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
    # this should be faster than the first version.
    # however, it uses the used_issuance_tuples list, which may grow and lead to memory problems
    ### it may be possible to categorize used_issuance_tuples by sender? But that would lead to additional overhead.
    # if the token is used very much.
    # it also depends from the list being sorted by timestamp. Must be ensured before (from the Once parser it seems that is the case).

    valid_issuances = []
    issuance_attempts = []
    regular_cards = []
    used_issuance_tuples = [] # this list joins all issuances of sender, txid, vout:
    oldtxid = ""

    # first, separate CardIssues from other cards
    # card.amount is a list, the sum must be equal to the amount of the tx * multiplier
    print([card.txid for card in cards])
    for card in cards:
        if card.type == "CardIssue":
            print("checking issuance ...")
            print("Deck datastring:", card.deck_data)
            print("Card datastring:", card.asset_specific_data)
            txid_b, vout_b = card.asset_specific_data.split(b":")[1:3]
            txid, vout = txid_b.decode("utf-8"), vout_b.decode("utf-8")
            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, txid, vout) not in used_issuance_tuples:
                # check 2: check if tx exists, sender is correct and amount corresponds to amount in tx (expensive!)
                ref_amount = sum(card.amount) / (10**card.number_of_decimals)
                if is_valid_issuance(provider, card.sender, tracked_address(card), txid, int(vout), ref_amount, multiplier(card)):
                    valid_issuances.append(card)
                    used_issuance_tuples.append((card.sender, txid, vout))
                    print("AT CardIssue:", card)
                else:
                    print("Ignoring CardIssue: Invalid data.")
            else:
                print("Ignoring CardIssue: Duplicate.")
        else:
            if card.txid != oldtxid:
                oldtxid = card.txid
                print("AT CardTransfer:", card.txid)
                regular_cards.append(card)

    return valid_issuances + regular_cards # does NOT check if the regular cards come from valid issuances (in "once" it also isn't the case)!


                
def parser_old(cards, provider):
    valid_issuances = []
    issuance_attempts = []
    regular_cards = []

    # first, separate CardIssues from other cards
    # check 1: check if the txid exist and the amount is correct
    for i in cards:
        if i.type == "CardIssue":
            txid, vout = i.asset_specific_data.split(b":")[1:3]
            txidstr, voutstr = txid.decode("utf-8"), vout.decode("utf-8")
            if is_valid_issuance(provider, txidstr, voutstr, i.amount, multiplier(i)):
                issuance_attempts.append(card)
        else:
            regular_cards.append(card)

    # check 2: eliminate all duplicates which reference the same transaction. Only the first of these is valid.
    for i in issuance_attempts:

        # for each issuance, find other cards from the same deck issued by the same sender
        sender_issuances = [ j for j in issuance_attempts if j.sender == i.sender ]
        # look for issuance referencing the same txid
        for k in [ l for l in sender_issuances if tracked_address(l) == tracked_address(k) ]:
            txattempts = {}
            transactions = []
            for tx in tracked_transactions(k):
                transactions.append(tx)
                if [amount_to_address(tracked_address(k), tx) * multiplier(k)] == k.amount:
                    txattempts.update({"tx" : tx, "card" : k})
            for tx in set(transactions):
                first_issue_for_tx = next([ m for m in txattempts if m["tx"] == tx ]) # this works only if all transactions are processed chronologically and this isn't changed by this algo. Otherwise the timestamp has to be checked for validity.
                # other idea could be that all duplicates are bogus (but would this be accepted?)
                valid_issuances.append(m["card"])

    return valid_issuances + regular_cards

def update_at_balance(deck, provider, account="", many=999, since=0):
    """This function checks if there are new transactions from the addresses from a selected account
       to the tracked address. If yes, it creates the AT transactions with the correct asset_specific_data.
       It may be a challenge to integrate that with pacli?"""
    tracked_address = tracked_address_from_deck(deck)
    tx_list = provider.listtransactions(account, many, since)
                
                
        
    

