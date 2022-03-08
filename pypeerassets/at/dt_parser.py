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
    """Basic parser loop. Loops through all cards by epoch."""

    # debug = True # uncomment for testing
    # print([(c.txid, c.sender, c.receiver, c.amount, c.blocknum) for c in cards])

    # TODO: This should not be necessary normally, why is the list not chronologically ordered?
    # TODO: Transactions in the same block must also be ordered by block position.
    cards.sort(key=lambda x: x.blocknum)

    if debug: print("Starting parser.")
    if not current_blockheight:
        current_blockheight = provider.getblockcount()

    # initial_parser_state enables to continue parsing from a certain blockheight or use the parser from "outside".
    # Use with caution.
    if initial_parser_state:
        pst = initial_parser_state
        debug = pst.debug
        if debug: print("Using initial parser state provided.")
        if not pst.start_epoch: # workaround, should be done more elegant. Better move the whole section to ParserState.__init__.
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

    for epoch in range(pst.start_epoch, pst.end_epoch):

        pst.epoch = epoch
        epoch_firstblock = deck.epoch_length * epoch
        epoch_lastblock = deck.epoch_length * (epoch + 1)

        if debug: print("\nChecking epoch", epoch, "from block", epoch_firstblock, "to", epoch_lastblock)

        # grouping cards per epoch

        lowpos = pos
        card_found = False
        for pos, card in enumerate(pst.initial_cards, start=lowpos):

            if debug: print("Card block height:", card.blocknum, "Position", pos, "Cards len", cards_len, "TXID", card.txid)
            # CardIssues before the first block of the epoch are always invalid.
            if not (epoch_firstblock <= card.blocknum <= epoch_lastblock):
                break
            card_found = True # TODO: This is probably necessary because enumerate doesn't add 1 to the index after every successful loop instance but at each re-start. Re-check!

        if card_found == True:
            pos += 1 # without this it won't work, e.g. if there is only 1 card - cards[0:0] # TODO Re-check!
        highpos = pos
        epoch_cards = cards[lowpos:highpos]

        if debug: print("Cards found in this epoch:", len(epoch_cards))


        # Epochs which have passed since the deck spawn
        # epochs_from_start = epoch - pst.start_epoch # MODIFIED. We use sdp_epochs_remaining instead, as epochs_from_start counts all epochs, not only the ones with completed proposals.
        sdp_epochs_remaining = deck.sdp_periods - pst.epochs_with_completed_proposals # TODO Re-check!

        # if debug: print("Epochs with completed proposals:", pst.epochs_with_completed_proposals)
        if debug: print("SDP periods remaining:", sdp_epochs_remaining)

        if (deck.sdp_periods > 0) and (sdp_epochs_remaining <= deck.sdp_periods): # voters from other tokens

            # We set apart all CardTransfers of SDP voters before the epoch start
            sdp_epoch_balances = pst.get_sdp_balances()

            # Weight is calculated according to the epoch
            # Weight is reduced only in epochs where proposals were completely approved.
            sdp_weight = get_sdp_weight(pst.epochs_with_completed_proposals, deck.sdp_periods)

            # Adjusted weight multiplies the token balance by the difference in decimal places
            # between the main token and the SDP token.
            # adjusted_weight = sdp_weight * 10 ** pst.sdp_decimal_diff

            if len(sdp_epoch_balances) > 0: # MODIFIED: was originally new_sdp_voters
                pst.enabled_voters.update(update_voters(pst.enabled_voters, sdp_epoch_balances, weight=sdp_weight, debug=pst.debug, dec_diff=pst.sdp_decimal_diff))

        # as card issues can occur any time after the proposal has been voted
        # we always need ALL valid proposals voted up to this epoch.

        #if pst.debug: print("Get ending proposals ...")
        #if pst.debug: print("Approved proposals before epoch", pst.epoch, pst.approved_proposals)
        pst.update_approved_proposals()
        # if debug: print("Approved proposals after epoch", pst.epoch, pst.approved_proposals)

        pst.update_valid_ending_proposals()
        # if debug: print("Valid ending proposals after epoch:", pst.epoch, pst.valid_proposals)

        if (highpos == lowpos) or len(epoch_cards) > 0:
            valid_epoch_cards = pst.get_valid_epoch_cards(epoch_cards)

        pst.enabled_voters.update(update_voters(voters=pst.enabled_voters, new_cards=valid_epoch_cards, debug=pst.debug))
        # if debug: print("New voters balances:", pst.enabled_voters)

        pst.valid_cards += valid_epoch_cards

        if (pos == cards_len) and not force_continue: # normally we don't need to continue if there are no cards left
            break

    if force_dstates:
        pst.force_dstates()

    return pst.valid_cards
