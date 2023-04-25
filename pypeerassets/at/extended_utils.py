# bundles functions for both AT and DT tokens.

def get_issuance_bundle(cards: list, i: int):
    # Due to pa.pautils.card_postprocess: if a card has multiple amounts,
    # it gets interpreted as a bundle.
    # This algorithm looks for multiple cards (equivalent to a CardBundle) in the same transaction.
    # This is necessary to allow payments in claim transactions.
    bundle_value = cards[i].amount[0]
    try:
        while cards[i].txid == cards[i + 1].txid:
            # if a bundle is detected, we perform a check to ensure the sender is identic
            # so possible future protocol changes (e.g. allowing multiple senders per tx) do not affect this.
            thiscard, nextcard = cards[i], cards[i + 1]
            if not thiscard.sender == nextcard.sender:
                break
            i += 1
            bundle_value += cards[i].amount[0]

    except IndexError:
        # if we're already at the end of the cards list, do not enter the loop.
        pass

    # we need to return the last index i: all cards until i will be valid/invalid if the first one is
    # TODO re-check the "all cards of bundle are invalid" part: if there could be an "attack" where one of the "sub-cards" is valid after the first one is not.
    return (bundle_value, i)
