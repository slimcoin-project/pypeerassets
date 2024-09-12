#!/usr/bin/env python3

""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch and then by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from pypeerassets.at.dt_parser_state import ParserState
from pypeerassets.at.extended_utils import process_cards_by_bundle

def dt_parser(cards: list, provider: object, deck: object, current_blockheight: int=None, initial_parser_state: object=None, force_dstates: bool=False, force_continue: bool=False, start_epoch: int=None, end_epoch: int=None, debug: bool=False, debug_voting: bool=False, debug_donations: bool=False):
    """Basic parser loop. Loops through all cards, and processes epochs."""

    cards.sort(key=lambda x: (x.blocknum, x.blockseq, x.cardseq))

    # initial_parser_state allows to use the parser without calling the
    # find_all_valid_cards function. Use with caution.

    if initial_parser_state:
        pst = initial_parser_state
        debug = pst.debug
        if debug: print("PARSER: Using initial parser state provided.")
        if pst.start_epoch is None: # workaround, should be done more elegant. Better move the whole section to ParserState.__init__.
            pst.start_epoch = start_epoch # normally start when the deck was spawned.
    else:
        pst = ParserState(deck, cards, provider, current_blockheight=current_blockheight, start_epoch=start_epoch, end_epoch=end_epoch, debug=debug, debug_voting=debug_voting, debug_donations=debug_donations)

    pst.init_parser()
    if debug: print("PARSER: Starting parser.")
    if pst.current_blockheight is None:
        pst.current_blockheight = provider.getblockcount()
    if debug: print("PARSER: Current blockheight:", pst.current_blockheight)

    if debug: print("PARSER: Starting epoch count at deck spawn block", pst.startblock)
    cards_len = len(pst.initial_cards)
    if debug: print("PARSER: Total number of initial cards:", cards_len)
    if debug: print("PARSER: Starting epoch loop ...")

    if not pst.end_epoch:
        pst.end_epoch = pst.current_blockheight // deck.epoch_length # NOTE: modified, still includes the incomplete epoch which just started

    if debug: print("PARSER: Start and end epoch:", pst.start_epoch, pst.end_epoch)

    valid_epoch_cards = []
    valid_bundles = []
    pst.epoch = pst.start_epoch
    epoch_initialized = False

    for (card, bundle_amount) in process_cards_by_bundle(cards, debug=debug):

        card_epoch = card.blocknum // deck.epoch_length # deck epoch count starts at genesis block
        if debug: print("PARSER: Next card {} in epoch {} - currently processing epoch: {}".format(card.txid, card_epoch, pst.epoch))

        if card_epoch > pst.end_epoch:
            break

        elif card_epoch > pst.epoch:
            # this happens if the card is located after the epoch we're currently processing
            # so it will happen:
            # 1) when all cards of an epoch have been processed and it's the next one's turn
            # 2) almost always in the first loop iteration,
            # 3) between epochs where no new cards were transferred.

            if len(valid_epoch_cards) > 0:
                # epoch_postprocess updates voters and valid_cards
                if debug: print("PARSER: Postprocessing cards of epoch {} ...".format(pst.epoch))
                pst.epoch_postprocess(valid_epoch_cards)
                valid_epoch_cards = []

            # epoch(s) without cards is/are processed.
            if debug: print("PARSER: Processing epochs without cards: {}-{}".format(pst.epoch, card_epoch - 1))
            pst.process_cardless_epochs(pst.epoch, card_epoch - 1)
            if debug: print("PARSER: Processing of cardless epochs finished at the end of epoch", pst.epoch)
            pst.epoch += 1 # setting epoch to card epoch, out from process_cardless_epochs
            epoch_initialized = False


        if card_epoch == pst.epoch: # NOTE: changed from elif to if, so it is called after the cardless epochs.

            # Processing the epoch with the current CardTransfer.
            if not epoch_initialized:
                pst.epoch_init()
                epoch_initialized = True

            issued_amount = card.amount[0] if bundle_amount is None else bundle_amount

            if (card.type == "CardIssue") and (card.txid in valid_bundles):
                # parts of valid CardIssue CardBundles which were already processed.
                valid_epoch_cards.append(card)

            if pst.check_card(card, issued_amount):
                # yield card  # original idea was to transform this into a generator, maybe later.
                valid_epoch_cards.append(card)
                if bundle_amount is not None:
                    valid_bundles.append(card.txid)

    if len(valid_epoch_cards) > 0:
        # TODO: postprocessing seems to have some problems, see in epoch 557: VOTING: New enabled dPoD voter: mtYvCVBtEayA5y6szGSrSgGwHQfe44Bgh2 with balance -100.
        if debug: print("PARSER: Postprocessing cards of FINAL epoch {} ...".format(pst.epoch))
        pst.epoch_postprocess(valid_epoch_cards)

    # if no more cards are recorded, we only process the rest until the current blockheight if force_continue was set
    #  i.e. for informational purposes. (e.g. proposal state or get_votes commands)

    if force_continue:
        if pst.epoch < pst.end_epoch:
            if debug: print("PARSER: FINAL processing of epochs without cards: {}-{}".format(pst.epoch, pst.end_epoch))
            pst.process_cardless_epochs(pst.epoch, pst.end_epoch)
            if debug: print("PARSER: FINAL processing of cardless epochs finished at the end of epoch", pst.epoch)
        else:
            if debug: print("PARSER: No epochs left to process after last card.")

    if force_dstates:
        pst.force_dstates()

    return pst.valid_cards
