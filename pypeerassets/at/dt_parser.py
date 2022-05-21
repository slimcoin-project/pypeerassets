#!/usr/bin/env python3

""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch, instead by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.transaction_formats import *
from pypeerassets.at.dt_parser_utils import *
from pypeerassets.at.dt_parser_state import ParserState

def dt_parser(cards, provider, deck, current_blockheight=None, debug=False, initial_parser_state=None, force_dstates=False, force_continue=False, start_epoch=None, end_epoch=None):
    """Basic parser loop. Loops through all cards, and processes epochs."""

    # debug = True # uncomment for testing
    # print([(c.txid, c.sender, c.receiver, c.amount, c.blocknum) for c in cards])

    # TODO: Transactions in the same block must also be ordered by block position.
    # Modified: added blockseq and cardseq.
    cards.sort(key=lambda x: (x.blocknum, x.blockseq, x.cardseq))

    if debug: print("Starting parser.")
    if current_blockheight is None:
        current_blockheight = provider.getblockcount()

    # initial_parser_state enables to continue parsing from a certain blockheight or use the parser from "outside".
    # Use with caution.
    if initial_parser_state:
        pst = initial_parser_state
        debug = pst.debug
        if debug: print("Using initial parser state provided.")
        if pst.start_epoch is None: # workaround, should be done more elegant. Better move the whole section to ParserState.__init__.
            pst.start_epoch = start_epoch # normally start when the deck was spawned.
    else:
        pst = ParserState(deck, cards, provider, current_blockheight=current_blockheight, start_epoch=start_epoch, end_epoch=end_epoch, debug=debug)

    pst.init_parser()

    if debug: print("Starting epoch count at deck spawn block", pst.startblock)

    cards_len = len(pst.initial_cards)
    if debug: print("Total number of cards:", cards_len)

    if debug: print("Starting epoch loop ...")
    # oldtxid = "" # probably obsolete
    pos = 0 # card position
    highpos = 0

    if not pst.end_epoch:
        pst.end_epoch = current_blockheight // deck.epoch_length + 1 # includes an incomplete epoch which just started

    if debug: print("Start and end epoch:", pst.start_epoch, pst.end_epoch)

    ### Loop changed temporarily from here, with new epoch_init and epoch_postprocess methods. EXPERIMENTAL!
    ### Loop goes through now and provides identic results for Proposal A.
    ### TODO: re-check all commands for equivalency!
    # first_epochs_processed = False
    pst.epoch = pst.start_epoch
    epoch_initialized = False
    epoch_completed = False

    for card in pst.initial_cards:

        card_epoch = card.blocknum // deck.epoch_length # as deck count start is from genesis block this is correct

        if card_epoch > pst.epoch:
            # this happens if the card is located after the epoch we're currently processing
            # so it will happen:
            # 1) when all cards of an epoch have been processed and it's the next one's turn
            # 2) almost always in the first loop iteration,
            # 3) between epochs where no new cards were transferred.

            if len(valid_epoch_cards) > 0:
                # normal epoch advancement: still the epoch cards were not processed
                pst.epoch_postprocess(valid_epoch_cards)
                valid_epoch_cards == []

            # epoch(s) without cards is/are processed.
            # TODO: is second argument card_epoch or card_epoch - 1??

            pst.process_cardless_epochs(pst.epoch, card_epoch - 1)

        if card_epoch == pst.epoch:

            # this should happen only if we're now processing the epoch with the current CardTransfer.
            if not epoch_initialized:
                pst.epoch_init()
                if debug: print("\nChecking epoch", self.epoch, "from block", epoch_firstblock, "to", epoch_lastblock)
                epoch_initialized = True

            if pst.check_card(card): # new method which checks only ONE card, replaces get_valid_epoch_cards
                # yield card
                valid_epoch_cards.append(card)

        # TODO: if this is transformed into a generator, check if we need to process something directly after the yield statement.

    # if no more cards are recorded, we only process the rest if force_continue was set, i.e. for informational purposes.
    # (e.g. proposal state or get_votes commands)
    if force_continue:
        pst.process_cardless_epochs(pst.epoch, pst.end_epoch)

    if force_dstates:
        pst.force_dstates()

    return pst.valid_cards
