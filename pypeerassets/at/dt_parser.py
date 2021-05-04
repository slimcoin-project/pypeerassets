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


# COIN_MULTIPLIER = 100000000 # only used for cards. # PROBABLY not needed.

def validate_proposer_issuance(pst, dtx_id, card_units, card_sender, card_blocknum):
    # MODIFIED: A large part has been moved to the ProposalState and DonationState classes.

    proposal_state = pst.valid_proposals[dtx_id] # this is checked just before the call, so no "try/except" necessary.

    # 1. Check if the card issuer is identical to the Proposer.
    if card_sender not in proposal_state.valid_ptx.input_addresses:
        if pst.debug: print("Proposer issuance failed: Incorrect card issuer.")
        return False

    # 2. Card must be issued after the last round deadline. Otherwise, a card could become valid for a couple of blocks.
    try:
       last_round_start = proposal_state.round_starts[8]
    except (IndexError, AttributeError):
       # if round_starts attribute is still not set , e.g. because there was not a single Donation CardIssue.
       # then we set all round starts.

       proposal_state.set_round_starts()
       last_round_start = proposal_state.round_starts[8]

    if card_blocknum < last_round_start:
        return False

    req_amount = proposal_state.valid_ptx.req_amount

    #if len(proposal_state.donation_txes) == 0:
    #    proposal_state.set_phase_txes_and_amounts(pst.donation_txes, "donation")
    if len(proposal_state.donation_states) == 0:
        proposal_state.set_donation_states()
    
    # TODO: the missing donation approach is probably better, anyway here we will use the proposer reward
    # DISCUSS: In this case it may be an alternative to use the total amount of effective slots (min(donation, slot)).
    # This would lead to more coins issued when the donations exceed the combined effective slots.
    #missing_donations = req_amount - proposal_state.total_donated_amount
    #proposer_slot = (Decimal(missing_donations) / req_amount) * pst.deck.epoch_quantity

    if card_units != proposal_state.proposer_reward:
        return False

    return True

def validate_donation_issuance(pst, dtx_id, dtx_vout, card_units, card_sender):

    """Main validation function for donations. Checks for each issuance if the donation was correct.
    The donation transaction ID is provided (by the issue transaction)
    and it is checked if it corresponds to a real donation."""

    # Possible improvement: raise exceptions instead of simply returning False?

    if pst.debug: print("Checking donation tx:", dtx_id)

    # check A: does proposal exist?
    if pst.debug: print("Valid proposals:", pst.valid_proposals)

    # TODO: we have here no DonationTransaction object
    # We will probably need to create the ProposalState searching in it for the donation txid.
    # Or alternatively for the donation txid in pst.donation_txes
    # Find a more efficient way! For now we will use the search ...
    # MODIFIED: for now we use a dict.
    try:
        dtx = pst.donation_txes[dtx_id]
    except KeyError:
        if pst.debug: print("Donation transaction not found or not valid.")
        return False

    try:
        proposal_state = pst.valid_proposals[str(dtx.proposal_txid)]
    except KeyError:
        if pst.debug: print("Proposal state does not exist or was not approved.")
        return False

    # We only associate donation/signalling txes to Proposals which really correspond to a card (token unit[s]) issued.
    # This way, fake/no participation proposals and donations with no associated card issue attempts are ignored,
    # which could be a way to attack the system with spam.

    if len(proposal_state.donation_states) == 0:
        proposal_state.set_donation_states(debug=pst.debug)

    if pst.debug: print("Total number of donation txes:", len([tx for r in proposal_state.donation_txes for tx in r ]))

    # check B: Does txid correspond to a real donation?
    # We go through the DonationStates per round and search for the dtx_id.
    # When we find it, we get the DonationState for the card issuance. 
    for rd_states in proposal_state.donation_states:
        for ds in rd_states.values():
            if ds.donation_tx.txid == dtx_id:
                break
            else:
                continue
        break

    # Check C: The card issuance transaction was signed really by the donor?
    if card_sender != ds.donor_address:
        return False

    if pst.debug: print("Initial slot:", ds.slot, "Effective slot:", ds.effective_slot)
    if pst.debug: print("Real donation", ds.donated_amount)
    if pst.debug: print("Card amount:", card_units)
    if pst.debug: print("Calculated reward:", ds.reward)
    if pst.debug: print("Distribution Factor", proposal_state.dist_factor)


    # Check D: Was the issued amount correct? 
    if card_units != ds.reward:
        if pst.debug: print("Incorrect issued token amount, different from the assigned slot.")
        return False
    else:
        return True

def get_valid_epoch_cards(pst, epoch_cards):

    # This is the loop which checks all cards in an epoch for validity.
    # It loops, in each epoch, through the current issuances and checks if they're associated to a valid donation.
    # CONVENTION: voters' weight is the balance at the start block of current epoch

    oldtxid = ""
    valid_cards = []

    if pst.debug: print("Cards:", [card.txid for card in epoch_cards])

    for card in epoch_cards:

        card_data = card.asset_specific_data

        if card.type == "CardIssue":

            # First step: Look for a matching DonationTransaction.
            dtx_id = card.donation_txid

            # dtx_vout should currently always be 2. However, the variable is kept for future modifications.
            dtx_vout_bytes = getfmt(card_data, CARD_ISSUE_DT_FORMAT, "out")
            dtx_vout = int.from_bytes(dtx_vout_bytes, "big")            

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, dtx_id, dtx_vout) in pst.used_issuance_tuples:

                if pst.debug: print("Ignoring CardIssue: Duplicate.")
                continue
            
            # TODO: most likely wrong! >> the units are already int so do not have to be changed!
            # The sum of all amounts (list of ints) is calculated and transformed to Decimal type
            # Then number of decimals is applied
            # The coin multiplier transforms the amount into Bitcoin Satoshis (0.00000001 coins),
            # even if the base unit is different (e.g. SLM, PPC). 
            # This is the base unit from PeerAssets, for cross-blockchain compatibility.

            card_units = sum(card.amount) # MODIFIED: this is already an int value based on the card base units!


            # Is it a proposer or a donation issuance?
            # Proposers provide ref_txid of their proposal transaction.
            # If this TX is in proposal_txes, AND they are the sender of the card and fulfill all requirements,
            # then they get the token to the proposal address.

            if (dtx_id in pst.valid_proposals) and validate_proposer_issuance(pst, dtx_id, card_units, card.sender, card.blocknum):

                if pst.debug: print("DT CardIssue (Proposer):", card)

            elif validate_donation_issuance(pst, dtx_id, dtx_vout, card_units, card.sender):

                if pst.debug: print("DT CardIssue (Donation):", card)

            else:

                if pst.debug: print("Ignoring CardIssue: Invalid data.")
                continue

            valid_cards.append(card) # MODIFIED. So cards of all types are returned chronologically.
            pst.used_issuance_tuples.append((card.sender, dtx_id, dtx_vout))

        else:

            if card.txid != oldtxid: # TODO: this check may be obsolete.

                oldtxid = card.txid
                if pst.debug: print("DT CardTransfer:", card.txid)
                valid_cards.append(card) # MODIFIED. So all cards are returned chronologically.

    return valid_cards


def dt_parser(cards, provider, deck, current_blockheight=None, debug=False, initial_parser_state=None, force_dstates=False, force_continue=False, start_epoch=None, end_epoch=None):
    # old order: (cards, provider, current_blockheight, deck, debug=False, initial_parser_state=None, force_dstates=False, force_continue=False, end_epoch=None)

    """Basic parser loop. Loops through all cards by epoch."""

    if debug: print("Starting parser.")
    if not current_blockheight:
        current_blockheight = provider.getblockcount()

    # initial_parser_state enables to continue parsing from a certain blockheight or use the parser from "outside".
    # Use with caution.
    if initial_parser_state:
        if debug: print("Using initial parser state provided.")
        pst = initial_parser_state
        if not pst.start_epoch: # workaround, should be done more elegant. Better move the whole section to ParserState.__init__.
            pst.start_epoch = start_epoch # normally start when the deck was spawned.
    else:
        pst = ParserState(deck, cards, provider, current_blockheight=current_blockheight, start_epoch=start_epoch, end_epoch=end_epoch, debug=debug)

    pst.init_parser()

    if pst.debug: print("Starting epoch count at deck spawn block", pst.startblock)

    cards_len = len(pst.initial_cards)
    if pst.debug: print("Total number of cards:", cards_len)

    if pst.debug: print("Starting epoch loop ...")
    # oldtxid = "" # probably obsolete
    pos = 0 # card position
    highpos = 0

    if not pst.end_epoch:
        pst.end_epoch = current_blockheight // deck.epoch_length + 1 # includes an incomplete epoch which just started

    if pst.debug: print("Start and end epoch:", pst.start_epoch, pst.end_epoch)
    
    for epoch in range(pst.start_epoch, pst.end_epoch):

        pst.epoch = epoch
        epoch_firstblock = deck.epoch_length * epoch
        epoch_lastblock = deck.epoch_length * (epoch + 1)

        if pst.debug: print("\nChecking epoch", epoch, "from block", epoch_firstblock, "to", epoch_lastblock)

        # grouping cards per epoch

        lowpos = pos

        while pos < cards_len:

            card = pst.initial_cards[pos] # TODO: this only works with a list, not with a generator.

            if pst.debug: print("Card blocknum (block height of confirmation):", card.blocknum)

            # Issues before the first block of the epoch are always invalid.
            if epoch_firstblock <= card.blocknum <= epoch_lastblock:
                pos += 1            
            else:
                break

        highpos = pos
        epoch_cards = cards[lowpos:highpos]

        if pst.debug: print("Cards found in this epoch:", len(epoch_cards))
        

        # Epochs which have passed since the deck spawn
        epochs_from_start = epoch - pst.start_epoch


        if pst.debug: print("SDP periods remaining:", (deck.sdp_periods - epochs_from_start))

        if (deck.sdp_periods != 0) and (epochs_from_start <= deck.sdp_periods): # voters from other tokens

            # We set apart all CardTransfers of SDP voters before the epoch start
            sdp_epoch_balances = get_sdp_balances(pst)

            # Weight is calculated according to the epoch
            # EXPERIMENTAL: modified, so weight is reduced only in epochs where proposals were completely approved.
            sdp_weight = get_sdp_weight(pst.epochs_with_completed_proposals, deck.sdp_periods)
            # sdp_weight = get_sdp_weight(epochs_from_start, deck.sdp_periods)

            if len(sdp_epoch_balances) > 0: # MODIFIED: was originally new_sdp_voters
                pst.enabled_voters.update(update_voters(pst.enabled_voters, sdp_epoch_balances, weight=sdp_weight, debug=pst.debug))

        # as card issues can occur any time after the proposal has been voted
        # we always need ALL valid proposals voted up to this epoch.

        if pst.debug: print("Get ending proposals ...")
        # pst.valid_proposals.update(get_valid_ending_proposals(pst, deck)) # modified for states
        if pst.debug: print("Approved proposals before epoch", pst.epoch, pst.approved_proposals)
        update_approved_proposals(pst)
        if pst.debug: print("Approved proposals after epoch", pst.epoch, pst.approved_proposals)

        update_valid_ending_proposals(pst)
        if pst.debug: print("Valid ending proposals:", pst.valid_proposals)

        if (highpos == lowpos) or len(epoch_cards) > 0:
            valid_epoch_cards = get_valid_epoch_cards(pst, epoch_cards)
    
        pst.enabled_voters.update(update_voters(voters=pst.enabled_voters, new_cards=valid_epoch_cards, debug=pst.debug))
        if pst.debug: print("New voters balances:", pst.enabled_voters)

        pst.valid_cards += valid_epoch_cards

        if (pos == cards_len) and not force_continue: # normally we don't need to continue if there are no cards left
            break

    if force_dstates:
        pst.force_dstates()

    return pst.valid_cards
