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


def process_cards_by_bundle(cards, debug: bool=False):
    # This generator function pre-processes the list of cards for AT and DT parsers.
    # It looks for bundles and returns a bundle of:
    #     (card object, total issued amount of the bundle, first position of bundle)
    # NOTE: we cannot limit the whole parser thing to CardIssues, because we don't want to sort cards again in DeckState.
    last_processed_position = 0
    first_processed_position = 0
    # used_issuance_tuples = [] # may be better managed in the parsers.
    for cindex, card in enumerate(cards):
        if cindex < last_processed_position:
            # in cards processed as part of a bundle, the issued amount is ignored
            # this can only happen in the case of CardIssues.
            yield (card, None)
        if card.type == "CardIssue":
            # we only process bundles of CardIssues.
            # For the validity of other types (CardTransfer/CardBurn) bundles don't matter.
            total_issued_amount, last_processed_position = get_issuance_bundle(cards, cindex)
            if cindex != last_processed_position:
                first_processed_position = cindex
                if debug:
                    print("Bundle detected from position", cindex, "to position", last_processed_position)
                    print("Total coins issued:", total_issued_amount)

                yield (card, total_issued_amount)
            else:
                yield (card, None) # no bundle detected, so card.amount can be used.
        elif card.type in ("CardTransfer", "CardBurn"):
            yield (card, None)

