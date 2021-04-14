"""Functions for slot allocation are grouped in this file, so it can be used in dt_states."""

from decimal import Decimal, getcontext, localcontext
from pypeerassets.at.dt_entities import TrackedTransaction, SignallingTransaction, LockingTransaction, DonationTransaction

def get_raw_slot(tx_amount: int, req_amount: int, slot_rest: int=None, total_amount: int=None, round_txes: list=None) -> int:
    """Calculates the slot (maximum donation amount which gets translated into tokens) in a normal round (rd1-3/5-6))."""

    if (total_amount is None) and round_txes:
        total_amount = sum([tx.amount for tx in round_txes])

    # print("Total amount", total_amount, "TX amount", tx_amount, "REQ amount", req_amount, "slot rest", slot_rest)
    # Decimal precision is set to 6 by peerassets. We need more precision here.
    with localcontext() as ctx:
        ctx.prec = 28
        tx_proportion = Decimal(tx_amount) / total_amount
        # print("tx proportion", tx_proportion)

        if slot_rest is None:
            max_slot = int(req_amount * tx_proportion)
        else:
            max_slot = int(slot_rest * tx_proportion)

    # print("Proportion", tx_proportion, "Max slot", max_slot)

    # Slot cannot be higher than the signalling transaction amount.
    # Otherwise, if donation amounts are higher than req_amount, slots would be higher than the signalled amounts.
    return min(tx_amount, max_slot)

def get_first_serve_slot(stx: SignallingTransaction, round_txes: list, slot_rest: int=0) -> int:
    """Calculates the slot in First come first serve rounds (4, 8)
    Assumes chronological order of txes (should work, otherwise we would need a function retrieving the block).
    Only accepts SignallingTXes, not reserve txes."""
    try:
        stx_pos = [t.txid for t in round_txes].index(stx.txid) # MODIFIED: now we use Txid as marker.
        amount_before_stx = sum([tx.amount for tx in round_txes[:stx_pos]])
        if amount_before_stx < slot_rest:
            return min(stx.amount, slot_rest - amount_before_stx)
        else:
            return 0
 
    except IndexError:
        return 0

def get_priority_slot(tx: TrackedTransaction, rtxes: list, stxes: list, av_amount: int, ramount: int=None, samount: int=None) -> int:
    """Calculates the slot in rounds with two groups of transactions with  different priority (rd 2, 3, 5 and 6).
    Reserve transactions in these rounds have a higher priority than signalling txes."""

    if not ramount:
        ramount = sum([t.reserved_amount for t in rtxes])
    if not samount:
        samount = sum([t.amount for t in stxes])
    # print(tx.txid, [r.txid for r in rtxes])
    if tx.txid in [r.txid for r in rtxes]:
        # print("TX in rtxes", ramount, samount)
        return get_raw_slot(tx.reserved_amount, av_amount, total_amount=ramount)
    elif tx.txid in [s.txid for s in stxes]:
        # print("TX in stxes", ramount, samount)
        slot_rest = max(0, av_amount - ramount)
        if slot_rest > 0:
            return get_raw_slot(tx.amount, slot_rest, total_amount=samount)

    return 0

def get_slot(tx: TrackedTransaction, dist_round: int, signalling_txes: list=None, locking_txes: list=None, donation_txes: list=None, signalled_amounts: list=None, reserved_amounts: list=None, locked_amounts: list=None, donated_amounts: list=None, first_req_amount: int=None, final_req_amount: int=None, effective_slots: list=None, effective_locking_slots: list=None) -> int:

    # This is the variant with prioritary groups in round 2/3 and 5/6.    
    # first 4 rounds require timelocks, so ProposalState.locked_amounts must be initalized.
    # This is only necessary if there were donations in the first phase.
    # TODO: Check for amount/reserved_amount problem.
    # TODO: slot_rest could be better an attribute of ProposalState (so it doesn't have to be calculated so many times)
    # -> proposal: call it available_slot_amount
    # MODIFIED: ProposalState is not given here.

    # Check transaction type (signalling or donation/locking):
    try:
        tx_amount = tx.reserved_amount
        if dist_round in (0, 3, 6, 7): # Reserve transactions are not valid in these rounds.
            return 0 # could perhaps be implemented as an Exception?
    except AttributeError: # if reserved_amount doesn't exist, it is a SignallingTransaction.
        tx_amount = tx.amount
    

    #if proposal_state:
    #    signalled_amounts = proposal_state.signalled_amounts
    #    signalling_txes = proposal_state.signalling_txes
    #    locked_amounts = proposal_state.locked_amounts
    #    donation_txes = proposal_state.donation_txes
    #    reserved_amounts = proposal_state.reserved_amounts
    #    donated_amounts = proposal_state.donated_amounts
    #    effective_slot_amounts = proposal_state.effective_slot_amounts
    #    first_req_amount = proposal_state.first_ptx.req_amount
    #    final_req_amount = proposal_state.valid_ptx.req_amount

    # print("All normal signalled amounts", signalled_amounts)
    # print("Dist round of current tx:", dist_round)
    
    if dist_round in (0, 1, 2, 3):
        req_amount = first_req_amount
        
        if not locked_amounts:
            locked_amounts = [0, 0, 0, 0]

        if dist_round == 0:
            return get_raw_slot(tx_amount, req_amount, total_amount=signalled_amounts[0])   

        slot_rest_rd0 = req_amount - effective_locking_slots[0]
        # print("slot rest rd0", slot_rest_rd0)

        if dist_round == 1:
            # in priority rounds, we need to check if the signalled amounts correspond to a donation in the previous round
            # These are added to the reserved amounts (second output of DonationTransactions).
            # MODIFIED: The reserve txes are now assigned to the round the Donation corresponds.
            # print("checking round 1", locking_txes[0], signalling_txes[1], reserved_amounts[0], signalled_amounts[1])
            return get_priority_slot(tx, rtxes=locking_txes[0], stxes=signalling_txes[1], av_amount=slot_rest_rd0, ramount=reserved_amounts[0], samount=signalled_amounts[1])

        slot_rest_rd1 = slot_rest_rd0 - effective_locking_slots[1]
    
        if dist_round == 2:
            return get_priority_slot(tx, rtxes=locking_txes[1], stxes=signalling_txes[2], av_amount=slot_rest_rd1, ramount=reserved_amounts[1], samount=signalled_amounts[2])

        slot_rest_rd2 = slot_rest_rd1 - effective_locking_slots[2]

        if dist_round == 3:
            return get_first_serve_slot(tx, signalling_txes[3], slot_rest=slot_rest_rd2)

    elif dist_round in (4, 5, 6, 7):
        # For second phase, we take the last valid Proposal Transaction to calculate the slot, not the first one.
        # This means if there is a modification of the requested amount, donations have to be modified.
        req_amount = final_req_amount

        not_donated_amount = req_amount - sum(effective_slots[:4])
        # print("Not donated amount", not_donated_amount)


        if dist_round == 4:
            # TODO: re-check this and the following rounds.
            # this is a complex round. Priority is as follows:
            # 1. Donors of rounds1-3 who have finished the donation of their slot.
            rtxes_phase1 = [dtx for rd in donation_txes[:4] for dtx in rd if dtx.reserved_amount > 0]
            reserved_amount_phase1 = sum(reserved_amounts[:4])
            # print(reserved_amount_phase1)
            return get_priority_slot(tx, rtxes=rtxes_phase1, stxes=signalling_txes[4], av_amount=not_donated_amount, ramount=reserved_amount_phase1, samount=signalled_amounts[4])
            
        slot_rest_rd4 = not_donated_amount - effective_slots[4]

        if dist_round == 5:
            # priority as follows:
            # 1. Donors of round 4 with second outputs
            # 2. signalling txes of rd 5. TODO: only donors? of which rounds?
            return get_priority_slot(tx, rtxes=donation_txes[4], stxes=signalling_txes[5], av_amount=slot_rest_rd4, ramount=reserved_amounts[4], samount=signalled_amounts[5])        

        slot_rest_rd5 = slot_rest_rd4 - effective_slots[5]

        if dist_round == 6:        
            return get_raw_slot(tx.amount, req_amount, slot_rest=slot_rest_rd5, total_amount=signalled_amounts[6])

        # slot_rest_rd6 = not_donated_amount - sum(proposal_state.effective_slots[4:7]) # why?
        slot_rest_rd6 = slot_rest_rd5 - effective_slots[6]

        if dist_round == 7:        
            return get_first_serve_slot(tx, signalling_txes[7], slot_rest=slot_rest_rd6)

    return 0 # if dist_round is incorrect
