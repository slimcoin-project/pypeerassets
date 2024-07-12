"""Functions for slot allocation are grouped in this file, so they can be used in dt_states."""

from decimal import Decimal, localcontext
from pypeerassets.at.dt_entities import TrackedTransaction, SignallingTransaction, LockingTransaction, DonationTransaction

def get_raw_slot(tx_amount: int, av_amount: int, total_amount: int=None, round_txes: list=None) -> int:
    """Calculates the slot (maximum donation amount which gets translated into tokens) in a normal round (rd0/6))."""

    if (total_amount is None) and round_txes:
        total_amount = sum([tx.amount for tx in round_txes])

    # Decimal precision is set to 15 by peerassets. We need more precision here.

    with localcontext() as ctx:
        ctx.prec = 28
        tx_proportion = Decimal(tx_amount) / total_amount
        max_slot = int(av_amount * tx_proportion)

    # Slot cannot be higher than the amount of the Signalling Transaction.

    return min(tx_amount, max_slot)


def get_first_serve_slot(stx: SignallingTransaction, round_txes: list, slot_rest: int=0) -> int:
    """Calculates the slot in First come first serve rounds (3, 7)
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

def get_priority_slot(tx: TrackedTransaction, rtxes: list, stxes: list, av_amount: int, ramount: int=None, samount: int=None, debug: bool=False) -> int:
    """Calculates the slot in rounds with two groups of transactions with  different priority (rd 2, 3, 5 and 6).
    Reserve transactions in these rounds have a higher priority than signalling txes."""

    if not ramount:
        ramount = sum([t.reserved_amount for t in rtxes])
    if not samount:
        samount = sum([t.amount for t in stxes])

    if debug:
        print("SLOT: tx txid:", tx.txid)
        print("SLOT: reserved amount: {}, signalled amount: {}, total available_amount: {}".format(ramount, samount, av_amount))

    if tx.txid in [r.txid for r in rtxes]:
        slot = get_raw_slot(tx.reserved_amount, av_amount, total_amount=ramount)
        if debug: print("SLOT: tx reserved amount:", tx.reserved_amount)

    elif tx.txid in [s.txid for s in stxes]:

        slot_rest = max(0, av_amount - ramount)
        if slot_rest > 0:
            slot = get_raw_slot(tx.amount, slot_rest, total_amount=samount)
        else:
            slot = 0

        if debug: print("SLOT: tx amount: {}, slot rest: {}".format(tx.amount, slot_rest))

    else:
        slot = 0
        if debug: print("Transaction not found.")
    if debug: print("SLOT: Calculated slot", slot)

    return slot
