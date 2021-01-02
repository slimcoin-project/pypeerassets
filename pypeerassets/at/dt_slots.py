"""Functions for slot allocation are grouped in this file, so it can be used in dt_entities."""

from decimal import Decimal

def get_raw_slot(tx_amount, req_amount, slot_rest=0, total_amount=None, round_txes=None):
    # calculates the slot (maximum donation amount which gets translated into tokens) in a round (rd1-3/5-6))
    # Important: This is NOT the token amount the donor gets, but the maximum proportion of the token amount per distribution round.
    # step 1: get signalling txes in round.
    # MODIFIED: optimized, so no heavy calculations are done always if total_amount is known

    if (total_amount is None) and round_txes:
        total_amount = sum([tx.amount for tx in round_txes])

    print("Total amount", total_amount, "TX amount", tx.amount, "REQ amount", req_amount, "slot rest", slot_rest)
    tx_proportion = Decimal(tx.amount) / total_amount

    if slot_rest == 0:
        max_slot = req_amount * tx_proportion
    else:
        max_slot = slot_rest * tx_proportion

    print("Proportion", tx_proportion, "Max slot", max_slot)

    # Slot cannot be higher than the signalling transaction amount.
    # Otherwise, if the req_amount is not filled, slots would be higher than the signalled amounts.
    return min(tx_amount, max_slot)

def get_first_serve_slot(stx, round_txes, slot_rest=Decimal(0)):
    # assumes chronological order of txes.
    # First serve slot do no accept Reserve TXes.
    try:
        stx_pos = round_txes.index(stx)
        amounts_to_stx = [ tx.signalled_amount for tx in round_txes[:stx_pos] ]
        if sum(amounts_to_stx) < slot_rest:
            return tx.signalled_amount
        else:
            return 0
 
    except IndexError:
        return 0

def get_priority_slot(tx, rtxes, stxes, av_amount, ramount=None, samount=None):
    # This function aims to eliminate redundancies in the rounds where two groups of transactions
    # have a different priority (rd 2, 3, 5 and 6).
    # Reserve transactions in these rounds have a higher priority than signalling txes.
    if not ramount:
        reserved_amount = sum([t.reserved_amount for t in rtxes])
    if not samount:
        reserved_amount = sum([t.amount for t in stxes])
    if tx in rtxes:
        return get_raw_slot(tx.reserved_amount, av_amount, total_amount=ramount)
    elif tx in stxes:
        slot_rest = req_amount - reserved_amount
        return get_raw_slot(tx.amount, slot_rest, total_amount=samount)
    else:
        return None

def get_slot(tx, dist_round, proposal_state=None, round_txes=None, signalled_amounts=None, locked_amounts=None, donated_amounts=None, first_req_amount=None, final_req_amount=None):

    # This is the variant with prioritary groups in round 2/3 and 5/6.    
    # first 4 rounds require timelocks, so ProposalState.locked_amounts must be initalized.
    # This is only necessary if there were donations in the first phase.
    # TODO: Check for amount/reserved_amount problem.
    # TODO: slot_rest could be better an attribute of ProposalState (so it doesn't have to be calculated so many times)
    # -> proposal: call it available_slot_amount

    if type(tx) in (DonationTransaction, LockingTransaction):
         tx_amount = tx.reserved_amount
    elif type(tx) == SignallingTransaction:
         tx_amount = tx.amount

    if proposal_state:
        signalled_amounts = proposal_state.signalled_amounts
        signalling_txes = proposal_state.signalling_txes
        locked_amounts = proposal_state.locked_amounts
        donation_txes = proposal_state.donation_txes
        reserved_amounts = proposal_state.reserved_amounts
        donated_amounts = proposal_state.donated_amounts
        effective_slot_amounts = proposal_state.effective_slot_amounts
        first_req_amount = proposal_state.first_ptx.req_amount
        final_req_amount = proposal_state.valid_ptx.req_amount

    print("All normal signalled amounts", signalled_amounts)
    print("Dist round of current tx:", dist_round)
    
    if dist_round in (0, 1, 2, 3):
        req_amount = first_req_amount
        
        if not locked_amounts:
            locked_amounts = [0, 0, 0, 0]

        if dist_round == 0:
            return get_raw_slot(tx_amount, req_amount, total_amount=signalled_amounts[0])   

        slot_rest_rd0 = req_amount - effective_locking_slots[0]

        if dist_round == 1:
            # in priority rounds, we need to check if the signalled amounts correspond to a donation in the previous round
            # These are added to the reserved amounts (second output of DonationTransactions).
            # MODIFIED: The reserve txes are now assigned to the round the Donation corresponds.
            return get_priority_slot(tx, rtxes=locking_txes[0], stxes=signalling_txes[1], av_amount=slot_rest_rd0, ramount=reserved_amounts[0], samount=signalled_amounts[1])

        slot_rest_rd1 = slot_rest_rd0 - effective_locking_slots[1]
    
        if dist_round == 2:
            return get_priority_slot(tx, rtxes=locking_txes[1], stxes=signalling_txes[2], av_amount=slot_rest_rd1, ramount=reserved_amounts[1], samount=signalled_amounts[2])

        slot_rest_rd2 = slot_rest_rd1 - effective_locking_slots[2]

        if dist_round == 3:
            return get_first_serve_slot(tx, signalling_txes[3], slot_rest=slot_rest_rd2)

    elif dist_round in (4, 5, 6, 7):
        # For second phase, we take the last valid Proposal Transaction to calculate slot, not the first one.
        # This means if there is a modification of the requested amount, donations have to be modified.
        req_amount = final_req_amount

        not_donated_amount = req_amount - sum(effective_slots[:4])
        print("Not donated amount", not_donated_amount)


        if dist_round == 4:
            # TODO: re-check this and the following rounds.
            # this is a complex round. Priority is as follows:
            # 1. Donors of rounds1-3 who have finished the donation of their slot.
            rtxes_phase1 = [dtx for rd in donation_txes[:4] for dtx in rd if dtx.reserved_amount > 0]
            reserved_amount_phase1 = sum(reserved_amounts[:4])
            return get_priority_slot(tx, rtxes=rtxes_phase1, stxes=signalling_txes[4], av_amount=not_donated_amount, ramount=reserved_amount_phase1, samount=signalled_amounts[4])
            
        slot_rest_rd4 = not_donated_amount - effective_slots[4]

        if dist_round == 5:
            # priority as follows:
            # 1. Donors of round 4 with second outputs
            # 2. signalling txes of rd 5. TODO: only donors? of which rounds?
            return get_priority_slot(tx, rtxes=donation_txes[4], stxes=signalling_txes[5], av_amount=slot_rest_rd4, ramount=reserved_amounts[4], samount=signalled_amounts[5])        

        slot_rest_rd5 = slot_rest_rd4 - effective_slots[5]

        if dist_round == 6:        
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd5, total_amount=signalled_amounts[6])

        # slot_rest_rd6 = not_donated_amount - sum(proposal_state.effective_slots[4:7]) # why?
        slot_rest_rd6 = slot_rest_rd5 - effective_slots[6]

        if dist_round == 7:        
            return get_first_serve_slot(tx, signalling_txes[7], slot_rest=slot_rest_rd6)

    return None # if dist_round is incorrect
