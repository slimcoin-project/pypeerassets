"""Functions for slot allocation are grouped in this file, so it can be used in dt_states."""

from decimal import Decimal, getcontext, localcontext
from pypeerassets.at.dt_entities import TrackedTransaction, SignallingTransaction, LockingTransaction, DonationTransaction

def get_raw_slot(tx_amount: int, av_amount: int, total_amount: int=None, round_txes: list=None) -> int:
    """Calculates the slot (maximum donation amount which gets translated into tokens) in a normal round (rd0/6))."""
    # MODIFIED: replaced req_amount and slot_rest with av_amount. There seems to be no reason for separating them.

    if (total_amount is None) and round_txes:
        total_amount = sum([tx.amount for tx in round_txes])

    # print("Total amount", total_amount, "TX amount", tx_amount, "REQ amount", req_amount, "slot rest", slot_rest)
    # Decimal precision is set to 6 by peerassets. We need more precision here.
    with localcontext() as ctx:
        ctx.prec = 28
        tx_proportion = Decimal(tx_amount) / total_amount
        max_slot = int(av_amount * tx_proportion)

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

def get_slot(ps: object, tx: TrackedTransaction, dist_round: int) -> int:

    # TODO better use the ps parameters directly.
    if ps is not None:
        signalling_txes = ps.signalling_txes
        locking_txes = ps.locking_txes
        donation_txes = ps.donation_txes
        reserve_txes = ps.reserve_txes
        signalled_amounts = ps.signalled_amounts
        reserved_amounts = ps.reserved_amounts
        locked_amounts = ps.locked_amounts
        donated_amounts = ps.donated_amounts
        effective_slots = ps.effective_slots
        effective_locking_slots = ps.effective_locking_slots
        available_amount = ps.available_slot_amount

    # This is only necessary if there were donations in the first phase.
    # Check transaction type (signalling or donation/locking):
    # This works because SignallingTransactions have no attribute .reserved_amount and thus throw AttributeError.
    try:
        tx_amount = tx.reserved_amount
        if dist_round in (0, 3, 6, 7): # Reserve transactions are not valid in these rounds.
            return 0 # could perhaps be implemented as an Exception?
    except AttributeError:
        tx_amount = tx.amount

    # First 4 rounds require timelocks, so ProposalState.locked_amounts must be initalized.
    if dist_round in (0, 1, 2, 3) and not locked_amounts:
        locked_amounts = [0, 0, 0, 0]

    if dist_round in (0, 6):
        # Note: available_amount[0] is the same than req_amount.
        return get_raw_slot(tx_amount, available_amount[dist_round], total_amount=signalled_amounts[dist_round])

    elif dist_round in (1, 2):
        # in priority rounds, we need to check if the signalled amounts correspond to a donation in the previous round
        # These are added to the reserved amounts (second output of DonationTransactions).
        # MODIFIED: The reserve txes are now assigned to the round the Donation corresponds.
        # print("checking round 1", locking_txes[0], signalling_txes[1], reserved_amounts[0], signalled_amounts[1])
        return get_priority_slot(tx, rtxes=locking_txes[dist_round - 1], stxes=signalling_txes[dist_round], av_amount=available_amount[dist_round], ramount=reserved_amounts[dist_round - 1], samount=signalled_amounts[dist_round])

    elif dist_round in (3, 7):
        return get_first_serve_slot(tx, signalling_txes[dist_round], slot_rest=available_amount[dist_round])

    elif dist_round == 4:
        # this is a complex round. Priority is as follows:
        # 1. Donors of rounds1-3 who have finished the donation of their slot.
        # rtxes_phase1 = [dtx for rd in donation_txes[:4] for dtx in rd if (dtx.reserved_amount is not None) and (dtx.reserved_amount > 0)] # MODIFIED and simplified.
        rtxes_phase1 = [rtx for rd in reserve_txes[:4] for rtx in rd]
        reserved_amount_phase1 = sum(reserved_amounts[:4])
        # print(reserved_amount_phase1)
        return get_priority_slot(tx, rtxes=rtxes_phase1, stxes=signalling_txes[4], av_amount=available_amount[4], ramount=reserved_amount_phase1, samount=signalled_amounts[4])

    elif dist_round == 5:
        # priority as follows:
        # 1. Donors of round 4 with second outputs
        # 2. signalling txes of rd 5.
        return get_priority_slot(tx, rtxes=donation_txes[4], stxes=signalling_txes[5], av_amount=available_amount[5], ramount=reserved_amounts[4], samount=signalled_amounts[5])

    else:
        return 0 # if dist_round is incorrect
