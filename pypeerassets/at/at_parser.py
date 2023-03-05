from pypeerassets.provider import Provider

"""
addresstrack_parser.py bundles all "heavy" functions for the parser which include the use of the RPC node/provider. It is complemented by addresstrack_identify.py.

TODO: Ensure: All CardIssues (also those issued by the deck issuer) are invalid if they're not referencing a transaction from the same address correctly. Should be already the case, but incorrect CardIssues by the deck issuer will have to be detected separately. Also "issuances to themselves" must be permitted (See protocol.py).

TODO: card.deck isn't possible as deck isn't an attribute of card (why?)
=> ANSWER: probably due to structure, card objects are created from a "deck"
Workaround: deck_data attribute for CardTransfer. Look later for a more elegant method.

"""
# new comments:
#NOTE: This first rework is only to change the protocol to Protobuf and the new card.* attributes.
#A second rework could include using btcpy objects like Transaction, TxIn, TxOut ...
#TODO: the "version" should be in the Deck object.
# NOTE: deck is now fed here from the parser_fn function.


# TODO: It could be simply defined by protocol that the vin which gets credited is the first one, then this would not be necessary. (See problem with possible "batched" burn/donation transactions.)
def vin_check(tx, address, version, provider, debug=False): # "address" seems to be for v1?
    if version == 1:
        # v0: Only one vin is permitted.
        if len(tx["vin"]) > 1:
            if debug:
                print("Error: More than one input is not permitted in AT V1.")
            return False
    elif version == 2:
        # v1: several vins are permitted, but all must be from the same address.
        input_address_set = set(input_addresses(tx, provider))
        if debug:
            print("Input addresses:", input_address_set)
        return (len(input_address_set) == 1)
        # return True
    elif version == 3:
        # v2: several vins are permitted. If there is a change address, biggest vins get fully credited.
        return True

# def is_valid_issuance(provider, sender, tracked_address, ref_txid, ref_vout, ref_amountsum, multiplier):
def is_valid_issuance(provider: Provider, card: object, tracked_address: str, multiplier: int, at_version: int=1, debug: bool=False) -> bool:

    # MODIF: sender, ref_txid, ref_vout and ref_amountsum are all retrievable from card object:
    # card.sender, card.donation_txid, card.donation_vout, sum(card.amount)
    # for this prototype, only spending transactions where the card issuer is the ONLY sender in the transaction are valid.
    # Transactions must have exactly 1 "vin", coming from the same address.
    # Otherwise, that would lead to more complex and slow (but doable) checks.
    # TODO see above, we could simply define the first one to be the one credited.
    # However, for PoB transactions with more than one sender, maybe the "check proportion" is not the worst idea.
    # IDEA: those who contribute inputs must all separately issue the card (a card can have only one sender).
    # Only thing we need to add then, is a consistent protocol "division" of the funds.

    # parser_version = 0
    total_issuance_amount = sum(card.amount) / (10**card.number_of_decimals)

    # check 1: txid must be valid
    try:
        tx = provider.getrawtransaction(card.donation_txid, 1) # MODIF
    except: # bad txid
        if debug:
            print("Error: Bad or non-existing txid.")
        return False
    # check 2: amount of the tx to the address must be bigger than issued amount * multiplier
    # MODIF: must now be exactly EQUAL.
    # This allows issuance of less cards than the "allowed" amount, but then the txid is "used" and can't be used in other issuance. (Could be restricted to the exact amount, discuss.)
    try:
        tx_amount = tx["vout"][card.donation_vout]["value"]
    except IndexError: # bad vout
        if debug:
            print("Error: Bad vout.")
        return False
    if (tx_amount * multiplier) != total_issuance_amount: # from > to
        if debug:
            print("Error: Issuance value too high:", tx_amount, "*", multiplier, "<", total_issuance_amount)
        return False
    # check 3: tracked address must be correct
    if tx["vout"][card.donation_vout]["scriptPubKey"]["addresses"][0] != tracked_address:
        if debug:
            print("Error: Incorrect address:", tx["vout"][card.donation_vout]["scriptPubKey"]["addresses"][0], "correct one:", tracked_address)
        return False
    # check 4: vin rule must correspond to version
    if not vin_check(tx, card.sender, at_version, provider, debug=debug):
        return False
    # check 5 (most expensive, thus last): Sender must be identical with the transaction sender.
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
    # it also depends from the list being sorted by timestamp. Must be ensured before (from the Once parser it seems that is the case).

    valid_cards = []
    issuance_attempts = []
    used_issuance_tuples = [] # this list joins all issuances of sender, txid, vout, to filter out duplicates:
    # oldtxid = ""

    #at_version = 1 if "version" not in deck_metadata else deck_metadata["version"]
    at_version = 2
    # TODO: version parameter still not handled in deck protobuf.

    # first, separate CardIssues from other cards
    # card.amount is a list, the sum must be equal to the amount of the tx * multiplier}
    if debug:
        print("All cards:", [card.txid for card in cards])
    for card in cards:
        if card.type == "CardIssue":
            if debug:
                print("checking issuance ...")
                # print("Deck metadata:", deck)

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, card.donation_txid, card.donation_vout) not in used_issuance_tuples:

                # check 2: check if tx exists, sender is correct and amount corresponds to amount in tx (expensive!)
                if is_valid_issuance(provider, card, deck.at_address, deck.multiplier, at_version, debug=debug):

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

# NOT NECESSARY. DeckState does this. For a "partial state" a method involving DeckState is better.
#def update_at_balance(deck, provider, account="", many=999, since=0):
#    """This function checks if there are new transactions from the addresses from a selected account
#       to the tracked address. If yes, it creates the AT transactions with the correct asset_specific_data.
#       It may be a challenge to integrate that with pacli?"""
#    tracked_address = tracked_address_from_deck(deck)
#    tx_list = provider.listtransactions(account, many, since)

def burn_address(network): # for tests
    if network.is_testnet:
        return mmSLiMCoinTestnetBurnAddress1XU5fu
    else:
        pass # mainnet burn addr.

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




