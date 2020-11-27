#!/usr/bin/env python3

""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch, instead by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, ProposalState, SignallingTransaction, DonationTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError, COIN_MULTIPLIER
from pypeerassets.at.transaction_formats import *
from pypeerassets.at.dt_parser_utils import *
from pypeerassets.at.dt_slots import get_slot, get_raw_slot, get_first_serve_slot
from pypeerassets.__main__ import find_all_valid_cards

class ParserState(object):
    """contains the current state of basic variables"""

    def __init__(self, deck, initial_cards, provider, proposal_states={}, valid_proposals={}, signalling_txes=None, donation_txes=None, voting_txes=None, epoch=None, start_epoch=None, used_issuance_tuples=[], valid_cards=[], enabled_voters={}, sdp_cards=[], current_blockheight=None, debug=False):

        self.deck = deck
        self.initial_cards = initial_cards
        self.provider = provider
        self.current_blockheight = current_blockheight

        self.valid_cards = valid_cards
        self.proposal_states = proposal_states
        self.valid_proposals = valid_proposals
        self.signalling_txes = signalling_txes
        self.donation_txes = donation_txes
        self.voting_txes = voting_txes # this is a dict, not list.

        # enabled_voters variable is calculated once per epoch, taking into account card issuances and card transfers.
        # enabled_voters are all voters with valid balances, and their balance.
        self.enabled_voters = enabled_voters
        # SDP voters/balances are stored as CardTransfers, so they can be easily retrieved with PeerAsset standard methods.
        self.sdp_cards = sdp_cards

        # used_issuance_tuples list joins all issuances of sender, txid, vout:
        self.used_issuance_tuples = used_issuance_tuples

        self.epoch = epoch
        self.start_epoch = start_epoch # needed for SDP

        self.debug = debug # print statements for debugging

def validate_proposer_issuance(pst, dtx_id, decimal_card_amount, card_sender, card_blocknum):

    proposal_state = pst.valid_proposals(dtx_id) # this is checked just before the call, so no "try/except" necessary.

    # 1. Check if the card issuer is identical to the Proposer.
    if proposal_state.valid_ptx.sender != card_sender:
        return False

    # 2. Card must be issued after the last round deadline. Otherwise, this card could become valid for a couple of blocks.
    try:
       last_round_start = proposal_state.round_starts[8]
    except (IndexError, AttributeError):
       # if round_starts is still not set, e.g. because there was not a single Donation CardIssue.
       # then we calculate it, because it's relatively unlikely it will be need to set properly (more efficient).
       epoch_start = (proposal_state.valid_ptx.end_epoch - 1) * pst.deck.epoch_length
       last_round_start = epoch_start + DEFAULT_SECURITY_PERIOD + DEFAULT_VOTING_PERIOD + (proposal_state.round_length * 8) 
    if card_blocknum < last_round_start:
        return False

    req_amount = proposal_state.valid_ptx.req_amount

    if len(proposal_state.donation_txes) == 0:
        proposal_state.set_phase_txes_and_amounts(pst.donation_txes, "donation")

    missing_donations = req_amount - proposal_state.total_donated_amount

    if card_satoshis != missing_donations * proposal_state.dist_factor:
        return False

    return True

def validate_donation_issuance(pst, dtx_id, dtx_vout, card_satoshis, move_txid):

    """Main validation function for donations. Checks for each issuance if the donation was correct.
    The donation transaction ID is provided (by the issue transaction)
    and it is checked if it corresponds to a real donation."""

    # Possible improvement: raise exceptions instead of simply returning False?

    if pst.debug: print("Checking donation tx:", dtx_id)

    dtx_ids = [ tx.txid for tx in pst.donation_txes ]
    dtx_pos = dtx_ids.index(dtx_id)
    dtx = pst.donation_txes[dtx_pos]

    # A checks: General donation transaction check.

    # check A1: does proposal exist?
    if pst.debug: print("Valid proposals:", pst.valid_proposals)

    try:
        proposal_state = pst.valid_proposals[str(dtx.proposal_txid)]
    except KeyError:
        if pst.debug: print("Proposal state does not exist.")
        return False

    # We only associate donation/signalling txes to a Proposal which really correspond to a card (token unit[s]) issued.
    # This way, fake/no participation proposals and donations with no associated card issue attempts are ignored,
    # which could be a way to attack the system with spam.

    if len(proposal_state.signalling_txes) == 0:
        proposal_state.set_phase_txes_and_amounts(pst.signalling_txes, "signalling")

    if len(proposal_state.donation_txes) == 0: 
        proposal_state.set_phase_txes_and_amounts(pst.donation_txes, "donation")

    if pst.debug: print("Number of txes in all rounds:", len([tx for r in proposal_state.donation_txes for tx in r ]))

    # check A2: is donation address correct?

    if str(dtx.address) != proposal_state.first_ptx.donation_address:

        if pst.debug: print("Incorrect donation address.")
        return False

    if dtx.epoch == proposal_state.start_epoch:

        # check A3a: if sent in first phase, it must be timelocked.
        # TODO: implementation to handle DDT of locked tx to unresponsive proposers.

        if dtx.timelock is None:

            if pst.debug: print("No timelock, in this donation round a timelock is expected.")
            return False

        # Timelock must be longer than start of slot allocation round 9.
        elif dtx.timelock < proposal_state.round_starts[9]:

            if pst.debug: print("Timelock too short, must reach end of second round slot allocation.")
            return False

        # check A3b: if with timelock: money must have been moved
        # this maybe can be integrated in the big ProposalState function
        elif not was_vout_moved(provider, dtx, move_txid):

            if pst.debug: print("Donation was not moved, can be claimed still by the Donor.")
            return False

        dist_phase_rounds = PHASE1_ROUNDS # Phase 1: early donations after first vote.

    elif dtx.epoch == proposal_state.end_epoch:

        dist_phase_rounds = PHASE2_ROUNDS # Phase 2: late donations after second vote.

    else:

        if pst.debug: print("Incorrect epoch.")
        return False # incorrect round -> invalid tx.

    # check round
    for dist_round in dist_phase_rounds:

        round_donations = proposal_state.donation_txes[dist_round] # new structure

        if pst.debug: print("All donations", round_donations, "donation tx", [dtx])

        if dtx in round_donations:
            break
    else:
        return False # donation transaction not found

    # check A6: was the transaction correctly signalled?
    # TODO: It could be better to attach the signalling tx to the donation tx, but only if we re-use this frequently
    # We don't need to re-check signalling tx, because correct "marking" is already done in get_marked_transactions, and amount is checked here.
    round_signalling_txes = proposal_state.signalling_txes[dist_round]

    # We check the inputs of the donation transaction, and if one of them corresponds to a correct signalling transaction,
    # or a donation transaction with reserved amount.
    input_transactions = [txin.txid for txin in dtx.ins]

    for stx in round_signalling_txes:
        if stx.txid in input_transactions:
            correct_signalling_tx = stx
            break

        #if pst.debug: print("Signalled amount:", stx.amount)
        #if pst.debug: print("Card amount in satoshi:", card_satoshis)

        # the donor must have signalled at least the amount of the card. They cannot issue more than signalled.
        # TODO this is wrong, as it doesn't take into account the token distribution. Maybe get rid of this check?
        #if card_satoshis < stx.amount:

        #    if pst.debug: print("Correct amount signalled.")
        #    break

    else:

        # If no signalling transaction is found, check for a donation transaction with reserved output.
        # This is only done in the rounds with priority groups: In round 1,2 and 5 it's the donations
        # inmediately before, in round 4 it's all donations in rounds 0-3.
        # In rounds 4 and 5 the donations are checked for validity (only valid_donations are counted).

        if dist_round in (1, 2):
            reserve_dtxes = proposal_state.donation_txes[dist_round - 1]

        elif dist_round == 4:
            reserve_dtxes = [d for rd in proposal_state.valid_donations[:4] for d in rd])
        elif dist_round == 5:
            reserve_dtxes = proposal_state.valid_donations[4])
        else:
            reserve_dtxes = [] # we can already break this for round 0, 3, 6 and 7.
 
        for reserve_dtx in reserve_dtxes:
            if reserve_dtx.txid in input_transactions:
                correct_signalling_tx = reserve_dtx
                break

        else:
            if pst.debug: print("Donation not signalled correctly.")
            return False

    # check A5: slot check - token amount must correspond to slot and proposal factor.
    # The slot is the "maximum proportion of the total donated coins" which can be transformed into tokens,
    # according to the slot rules of each round.

    # card_satoshis is the card amount if it were measured in satoshis (so it's always int)
    # Important: The slot uses the Bitcoin (not the Peercoin) satoshi as its base unit (0.00000001). 
    # This means, all "COIN" values have to be multiplied by the COIN_MULTIPLIER (100000000)

    # TODO: Review if get_slot takes into account the new dist_factor, which is calculated only once per proposal.

    # The slot is the optimal donation amount.
    slot = get_slot(correct_signalling_tx, proposal_state, round_donations, dist_round)

    # The effective slot is the real amount to be taken into account as slot.
    # If the donor donated more than his slot, he does not get the right to issue more tokens.
    effective_slot = min(slot, dtx.amount)

    if pst.debug: print("Slot", slot)
    if pst.debug: print("Real donation", dtx.amount)
    if pst.debug: print("Card amount in satoshi", card_satoshis)
    if pst.debug: print("Distribution Factor", proposal_state.dist_factor)

    # The allowed amount is the proportion of the slot in relation to the complete required amount of the Proposal, token quantity per epoch.
    slot_proportion = Decimal(effective_slot) / proposal_state.req_amount
    allowed_amount = slot_proportion * deck.epoch_quantity * proposal_state.dist_factor

    if card_satoshis > allowed_amount:
        if pst.debug: print("Incorrect amount, higher than assigned slot.")
        return False
    else:
        return True

def get_valid_epoch_cards(pst, epoch_cards):

    # This is the loop which finds all valid cards in an epoch.
    # It loops, in each epoch, through the current issuances and checks if they're associated to a valid donation.
    # CONVENTION: voters' weight is the balance at the start block of current epoch

    oldtxid = ""
    valid_cards = []

    if pst.debug: print("Cards:", [card.txid for card in epoch_cards])

    for card in epoch_cards:

        card_data = card.asset_specific_data

        if card.type == "CardIssue":

            # dtx_vout should currently always be 2. However, the variable is kept for future modifications.
            # dtx_id_bytes = getfmt(card_data, CARD_ISSUE_DT_FORMAT, "dtx")
            dtx_vout_bytes = getfmt(card_data, CARD_ISSUE_DT_FORMAT, "out")

            #dtx_id = dtx_id_bytes.hex()
            dtx_id = card.donation_txid
            dtx_vout = int.from_bytes(dtx_vout_bytes, "big")            

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, dtx_id, dtx_vout) in pst.used_issuance_tuples:

                if pst.debug: print("Ignoring CardIssue: Duplicate.")
                continue
             
            # the sum of all amounts (list of ints) is calculated and transformed to Decimal type
            # then number of decimals applied
            # multiplier is not needed here: it is applied in validate_donation_issuance
            card_satoshis = Decimal(sum(card.amount)) / (10**card.number_of_decimals) * COIN_MULTIPLIER

            # Is it a proposer or a donation issuance?
            # Proposers provide ref_txid of their proposal transaction.
            # If this TX is in proposal_txes, AND they are the sender of the card and fulfill all requirements,
            # then they get the token to the proposal address.

            if (dtx_id in pst.valid_proposals) and validate_proposer_issuance(pst, dtx_id, card_satoshis, card.sender, card.blocknum):

                if pst.debug: print("DT CardIssue (Proposer):", card)

            elif validate_donation_issuance(pst, dtx_id, dtx_vout, card_satoshis, card.move_txid):

                if pst.debug: print("DT CardIssue (Donation):", card)

            else:

                if pst.debug: print("Ignoring CardIssue: Invalid data.")
                continue

            valid_cards.append(card) # MODIFIED. So cards of all types are returned chronologically.
            pst.used_issuance_tuples.append((card.sender, dtx_id, dtx_vout))

        else:

            if card.txid != oldtxid: # TODO: this check may be obsolete.

                oldtxid = card.txid
                print("DT CardTransfer:", card.txid)
                valid_cards.append(card) # MODIFIED. So all cards are returned chronologically.

    return valid_cards


def dt_parser(cards, provider, current_blockheight, deck, debug=True):

    """Basic parser loop. Loops through all cards by epoch."""

    if debug: print("Starting parser.")

    # prepare the loop
    deckspawn_blockhash = provider.getrawtransaction(deck.id, 1)["blockhash"]
    deckspawn_block = provider.getblock(deckspawn_blockhash)["height"]
    start_epoch = deckspawn_block // deck.epoch_length # Epoch count is from genesis block
    startblock = start_epoch * deck.epoch_length # first block of the epoch the deck was spawned.

    if deck.sdp_deck != None:
        sdp_cards = find_all_valid_cards(provider, deck.sdp_deck)
    else:
        sdp_cards = None

    pst = ParserState(deck, cards, provider, current_blockheight=current_blockheight, start_epoch=start_epoch, debug=debug)

    if pst.debug: print("Starting epoch count at deck spawn block", startblock)

    cards_len = len(pst.initial_cards)

    if pst.debug: print("Total number of cards:", cards_len)

    oldtxid = ""
    pos = 0 # card position
    highpos = 0
    current_epoch = current_blockheight // deck.epoch_length + 1 # includes an incomplete epoch which just started

    multiplier = pst.deck.multiplier

    if pst.debug: print("Get donation txes ...", )
    pst.donation_txes = get_donation_txes(provider, deck)
    if pst.debug: print(len(pst.donation_txes), "found.")

    if pst.debug: print("Get signalling txes ...", )
    pst.signalling_txes = get_signalling_txes(provider, deck)
    if pst.debug: print(len(pst.signalling_txes), "found.")

    if pst.debug: print("Get proposal states ...", )
    pst.proposal_states = get_proposal_states(provider, deck, current_blockheight, pst.signalling_txes, pst.donation_txes)
    if pst.debug: print(len(pst.proposal_states), "found.")

    if pst.debug: print("Get voting txes ...", )
    pst.voting_txes = get_voting_txes(provider, deck)
    if pst.debug: print(len(pst.voting_txes), "voting transactions found.")

    if pst.debug: print("Starting epoch loop ...")
    
    for epoch in range(start_epoch, current_epoch):

        pst.epoch = epoch
        epoch_firstblock = deck.epoch_length * epoch
        epoch_lastblock = deck.epoch_length * (epoch + 1)

        if pst.debug: print("Checking epoch", epoch, "from block", epoch_firstblock, "to", epoch_lastblock)

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
        if pst.debug: print("SDP periods:", deck.sdp_periods)

        # Epochs which have passed since the deck spawn
        epochs_from_start = epoch - pst.start_epoch

        if (deck.sdp_periods != 0) and (epochs_from_start <= deck.sdp_periods): # voters from other tokens

            # We set apart all CardTransfers of SDP voters before the epoch start
            sdp_epoch_balances = get_sdp_balances(pst)

            # Weight is calculated according to the epoch
            sdp_weight = get_sdp_weight(epochs_from_start, deck.sdp_periods)

            if len(new_sdp_voters) > 0:
                pst.enabled_voters.update(update_voters(pst.enabled_voters, sdp_epoch_balances, weight=sdp_weight))

        # as card issues can occur any time after the proposal has been voted
        # we always need ALL valid proposals voted up to this epoch.

        if pst.debug: print("Get ending proposals ...")
        pst.valid_proposals.update(get_valid_ending_proposals(pst, deck)) # modified for states
        if pst.debug: print("Valid ending proposals:", pst.valid_proposals)

        if (highpos == lowpos) or len(epoch_cards) > 0:
            valid_epoch_cards = get_valid_epoch_cards(pst, epoch_cards)
    
        pst.enabled_voters.update(update_voters(voters=pst.enabled_voters, new_cards=valid_epoch_cards))
        if pst.debug: print("New voters balances:", pst.enabled_voters)

        pst.valid_cards += valid_epoch_cards

        if pos == cards_len: # we don't need to continue if there are no cards left
            break

    return pst.valid_cards
