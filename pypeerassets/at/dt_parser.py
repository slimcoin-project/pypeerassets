#!/usr/bin/env python3

""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch and then by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from pypeerassets.at.dt_parser_state import ParserState

def dt_parser(cards: list, provider: object, deck: object, current_blockheight: int=None, initial_parser_state: object=None, force_dstates: bool=False, force_continue: bool=False, start_epoch: int=None, end_epoch: int=None, debug: bool=False, debug_voting: bool=False, debug_donations: bool=False):
    """Basic parser loop. Loops through all cards, and processes epochs."""

    # TODO: Transactions in the same block must also be ordered by block position.
    cards.sort(key=lambda x: (x.blocknum, x.blockseq, x.cardseq))

    # initial_parser_state enables to continue parsing from a certain blockheight or use the parser from "outside".
    # Use with caution.
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

    pos = 0 # card position
    highpos = 0

    if not pst.end_epoch:
        pst.end_epoch = pst.current_blockheight // deck.epoch_length + 1 # includes an incomplete epoch which just started

    if debug: print("PARSER: Start and end epoch:", pst.start_epoch, pst.end_epoch)

    ### MODIFIED: Loop changed from here, with new epoch_init and epoch_postprocess methods.
    ### Loop goes through now and provides identic results for Proposal A.
    ### TODO: maybe integrate into ParserState.
    # first_epochs_processed = False
    valid_epoch_cards = []
    pst.epoch = pst.start_epoch
    epoch_initialized = False
    # epoch_completed = False # probably not needed:
    # We complete always when we have valid_epoch_cards at the start of the loop or after the loop has ended.

    for card in pst.initial_cards:

        card_epoch = card.blocknum // deck.epoch_length # as deck count start is from genesis block this is correct
        if debug: print("PARSER: Checking card", card.txid, "in epoch", card_epoch, "- current epoch:", pst.epoch)

        if card_epoch > pst.epoch:
            # this happens if the card is located after the epoch we're currently processing
            # so it will happen:
            # 1) when all cards of an epoch have been processed and it's the next one's turn
            # 2) almost always in the first loop iteration,
            # 3) between epochs where no new cards were transferred.

            if len(valid_epoch_cards) > 0:
                # epoch_postprocess updates voters and valid_cards
                if debug: print("PARSER: Postprocessing cards of this epoch ...")
                pst.epoch_postprocess(valid_epoch_cards)
                valid_epoch_cards == []

            # epoch(s) without cards is/are processed.
            # TODO: is second argument card_epoch or card_epoch - 1??
            if debug: print("PARSER: Processing epochs without cards: {}-{}".format(pst.epoch, card_epoch - 1))
            pst.process_cardless_epochs(pst.epoch, card_epoch - 1)
            epoch_initialized = False
            if debug: print("PARSER: Processing of cardless epochs finished at epoch", pst.epoch)

        if card_epoch == pst.epoch:

            # Processing the epoch with the current CardTransfer.
            if not epoch_initialized:
                pst.epoch_init()
                epoch_initialized = True

            if pst.check_card(card): # new method which checks only ONE card, replaces get_valid_epoch_cards
                # yield card
                # TODO: if the loop is transformed into a generator,
                # check if we need to process something directly after the yield statement.
                valid_epoch_cards.append(card)


    if len(valid_epoch_cards) > 0:
        pst.epoch_postprocess(valid_epoch_cards)

    # if no more cards are recorded, we only process the rest until the current blockheight if force_continue was set
    #  i.e. for informational purposes. (e.g. proposal state or get_votes commands)

    if force_continue:
        pst.process_cardless_epochs(pst.epoch, pst.end_epoch)

    if force_dstates:
        pst.force_dstates()

    return pst.valid_cards
