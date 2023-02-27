from pypeerassets.at.dt_slots import get_raw_slot, get_first_serve_slot, get_priority_slot
from pypeerassets.at.dt_entities import TrackedTransaction, ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, InvalidTrackedTransactionError
from decimal import Decimal
from copy import deepcopy

# TODO: proposal states before the first voting round are currently marked as abandoned, this should not be so.

class ProposalState(object):
   # A ProposalState unifies all functions from proposals which are mutable.
   # i.e. which can change after the first proposal transaction was sent.


    def __init__(self, valid_ptx: ProposalTransaction, first_ptx: ProposalTransaction, all_signalling_txes: int=None, all_locking_txes: int=None, all_donation_txes: int=None, all_voting_txes: int=None, **sub_state):
        # MODIFIED: removed provider and current_blockheight. Isn't needed here probably.

        self.first_ptx = first_ptx # First ProposalTransaction of the ProposalState..
        self.valid_ptx = valid_ptx # Last proposal transaction which is valid.

        self.req_amount = self.valid_ptx.req_amount # should work with ProposalModifications due to side effect
        self.id = self.first_ptx.txid # Identification. Does not change with Modifications.

        # The round length of the second phase (not the first one) can be changed in ProposalModifications.
        # Thus all values based on round_length have 2 values, for the first and the second phase.
        self.round_lengths = [self.first_ptx.round_length, self.valid_ptx.round_length] # should work with ProposalModifications due to side effect
        self.donation_address = self.first_ptx.donation_address
        self.deck = self.first_ptx.deck

        # Slot Allocation Round Attributes are lists with values for each of the 8 distribution rounds
        # Phase 2 can vary if there is a ProposalModification, so this can be set various times.
        self.set_rounds(phase=0)

        # TODO: do we really still need provider and current_blockheight? Normally it should not be necessary here.
        # TODO: disabling it, but re-check well!
        #if not current_blockheight and (not signalling_txes or not donation_txes):
        #    current_blockheight = provider.getblockcount()

        self.init_fresh_state()

        if sub_state:
            for key, value in sub_state.items():
                self.__setattr__(key, value)

    def init_fresh_state(self):

        self.donor_addresses = []
        # New: Attributes for all TrackedTransactions without checking them (with the exception of VotingTransactions)
        self.all_signalling_txes = []
        self.all_locking_txes = []
        self.all_donation_txes = []
        self.all_voting_txes = []

        # The following attributes are set by the parser once a proposal ends.
        # Only valid transactions are recorded in them.
        self.signalling_txes = [[],[],[],[],[],[],[],[]]
        self.signalled_amounts = [0, 0, 0, 0, 0, 0, 0, 0]
        self.locking_txes = [[],[],[],[],[],[],[],[]]
        self.locked_amounts = [0, 0, 0, 0, 0, 0, 0, 0]
        self.donation_txes = [[],[],[],[],[],[],[],[]]
        self.donated_amounts = [0, 0, 0, 0, 0, 0, 0, 0]
        self.donation_states = []
        self.total_donated_amount = None
        self.reserve_txes = [[],[],[],[],[],[],[],[]]
        self.reserved_amounts = [0, 0, 0, 0, 0, 0, 0, 0]

        # Votes are set after the start and the end phase.
        self.voting_txes = [[],[]]
        self.initial_votes = None
        self.final_votes = None

        # The effective slot values are the sums of the effective slots in each round.
        self.effective_locking_slots = [0, 0, 0, 0]
        self.effective_slots = [0, 0, 0, 0, 0, 0, 0, 0]
        # Available slot amount: part of the req_amount which is still available for slots.
        self.available_slot_amount = [0, 0, 0, 0, 0, 0, 0, 0]

        # State: The general state of the proposal. Can be "active", "complete" or "abandoned".
        # At the start until the first voting round it is set to active.
        self.state = "active"

        # Factor to be multiplied with token amounts, between 0 and 1.
        # It depends on the Token Quantity per distribution period
        # and the number of coins required by the proposals in their ending period.
        # The higher the amount of proposals and their required amounts, the lower this factor is.
        self.dist_factor = None
        # Processed is a list of 3 values and refers to the donation states processed in each of both phases and the
        # completeness (i.e. if there were blocks missing for the last processed phase):
        # [ phase1, phase2, complete ]
        self.processed = [False, False, False] # TODO: delete third one, no longer needed! # re-checking ...

        # If there are slots missing at the end, the proposer can claim the proportion.
        self.proposer_reward = None


    def set_rounds(self, phase=0):
        # This method sets the start and end blocks of all rounds and periods of either the first or the second phase.
        # Phase 0 means: both phases are calculated.
        # Method is only called once per phase or when a proposal has been modified.

        # 1. Calculate round starts
        epoch_length = self.deck.epoch_length
        round_starts = [None] * 8 # all changed from 9 to 8
        round_halfway = [None] * 8

        if phase != 2: # BUGFIX: Modifications should not get rounds set to None.

            self.rounds = [None] * 8
            self.security_periods = [None] * 2
            self.voting_periods = [None] * 2
        security_period_lengths = [max(l // 2, 2) for l in self.round_lengths] # minimum 2 blocks
        voting_period_lengths = [l * 4 for l in self.round_lengths]
        release_period_length = voting_period_lengths[1] # MODIF: changed from voting_period_lengths[0].

        halfways = [l // 2 for l in self.round_lengths]

        pre_allocation_period_phase1 = security_period_lengths[0] + voting_period_lengths[0]
        pre_allocation_period_phase2 = security_period_lengths[1] + voting_period_lengths[1] + release_period_length


        if phase in (0, 1):
            distribution_length = pre_allocation_period_phase1 + (self.round_lengths[0] * 4)
            # blocks in epoch: blocks which have passed since last epoch start.
            blocks_in_epoch = self.first_ptx.blockheight % epoch_length
            blocks_remaining = epoch_length - blocks_in_epoch

            # if proposal can still be voted and slots distributed in the current epoch, then do it,
            # otherwise the voting/distribution phase will start in the next epoch.
            if blocks_remaining > distribution_length:

                # start_epoch is the epoch number of the first voting/distribution phase.
                self.start_epoch = self.first_ptx.epoch
                # dist_start is the block where the first voting/distribution phase starts.
                self.dist_start = self.first_ptx.blockheight
            else:
                self.start_epoch = self.first_ptx.epoch + 1
                self.dist_start = self.start_epoch * epoch_length

            # Security, voting and release periods
            self.security_periods[0] = [self.dist_start, self.dist_start + security_period_lengths[0] - 1] # FIX: added -1, otherwise we have one block more!
            voting_p1_start = self.security_periods[0][1] + 1
            self.voting_periods[0] = [voting_p1_start, voting_p1_start + voting_period_lengths[0] - 1] # FIX: added -1

            phase_start = self.dist_start + pre_allocation_period_phase1

            for rd in range(4): # first phase has 4 rounds
                round_starts[rd] = phase_start + self.round_lengths[0] * rd
                round_halfway[rd] = round_starts[rd] + halfways[0]
                self.rounds[rd] = [[round_starts[rd], round_halfway[rd] - 1], [round_halfway[rd], round_starts[rd] + self.round_lengths[0] - 1]]

        if phase in (0, 2):
            # we use valid_ptx here, this gives the option to change the round length of 2nd round.

            # epoch = self.end_epoch # final vote/distribution should always begin at the start of the end epoch.

            # End epoch is 1 after last working epoch.
            self.end_epoch = self.start_epoch + self.valid_ptx.epoch_number + 1
            end_epoch_start = self.end_epoch * epoch_length
            phase_start = self.end_epoch * epoch_length + pre_allocation_period_phase2

            self.security_periods[1] = [end_epoch_start, end_epoch_start + security_period_lengths[1] - 1] # FIX
            voting_p2_start = self.security_periods[1][1] + 1
            self.voting_periods[1] = [voting_p2_start, voting_p2_start + voting_period_lengths[1] - 1] # FIX

            release_start = self.voting_periods[1][1] + 1
            self.release_period = [release_start, release_start + release_period_length - 1] # FIX

            for i in range(4): # second phase has 4 rounds
                rd = i + 4
                round_starts[rd] = phase_start + self.round_lengths[1] * i
                round_halfway[rd] = round_starts[rd] + halfways[1] # MODIF: instead of "halfway"
                self.rounds[rd] = [[round_starts[rd], round_halfway[rd] - 1], [round_halfway[rd], round_starts[rd] + self.round_lengths[1] - 1]]

    def modify(self, debug=False):
        # This function bundles the modifications needed when a valid Proposal Modification was recorded.
        # It does not reprocess set_donation_states, because this is only done after end_epoch
        # when a card is detected or when the parser loop ends before end_epoch.
        # Thus set_donation_states is never called before modify.

        # 1: Re-setting rounds and other values for phase 2.
        if self.first_ptx.epoch_number != self.valid_ptx.epoch_number:
            self.set_rounds(phase=2)
            self.end_epoch = self.start_epoch + self.valid_ptx.epoch_number

        # 2. Re-setting required coin amount and derivative attributes
        if self.first_ptx.req_amount != self.valid_ptx.req_amount:
            self.req_amount = self.valid_ptx.req_amount

        if debug:
            print("PROPOSAL: Valid modification of proposal {} by transaction {}.\nreq_amount: {}, end_epoch: {}, rounds: {}".format(self.first_ptx.txid, self.valid_ptx.txid, self.req_amount, self.end_epoch, self.rounds))

    def set_donation_states(self, phase=0, current_blockheight=None, debug=False):
        # Phase 0 means both phases are calculated.

        # If rounds are not set, or phase is 2 (re-defining of the second phase), then we set it.
        if len(self.rounds) == 0 or (phase == 2):
            if debug: print("PROPOSAL: Setting rounds for proposal:", self.id)
            self.set_rounds(phase)

        # Mark abandoned donation states:
        # if called from "outside", if the block height > round end, otherwise when the dist_factor is set (ending period).
        # abandon_until marks all incomplete states as abandoned if they're checked in a certain round.
        if current_blockheight is not None:
            for rev_r, r_blocks in enumerate(reversed(self.rounds)):
                if current_blockheight > r_blocks[1][1]: # last block of each locking/donation round
                    abandon_until = 7 - rev_r # reversed order
                    break
                else:
                    abandon_until = 0

        elif self.dist_factor is not None:
            abandon_until = 7 # all incomplete are marked as abandoned if the parser sets the dist factor
        else:
            abandon_until = 0 # nothing is marked as abandoned

        # If the first phase is re-processed or if there was a incomplete processing:
        # -- the donor address list is reset
        if phase in (0, 1) or self.processed[2] == False:
            self.donor_addresses = []
        if phase in (0, 1):
            # Set the first available slot amout to req_amount.
            # If phase = 2, then the phase 1 values should be already set.
            self.available_slot_amount = [self.req_amount, None, None, None, None, None, None, None]

        self.donation_states = dstates = [{} for i in range(8)] # dstates is a list containing a dict with the txid of the signalling or reserve transaction as key


        # Once the proposal has ended and the number of proposals is known, the reward of each donor can be set
        set_reward = True if self.dist_factor is not None else False

        rounds = (range(8), range(4), range(4,8))

        # Sort all transactions
        self.all_signalling_txes.sort(key = lambda x: (x.blockheight, x.blockseq))
        self.all_locking_txes.sort(key = lambda x: (x.blockheight, x.blockseq))
        self.all_donation_txes.sort(key = lambda x: (x.blockheight, x.blockseq))

        # set direct successors
        # TODO: this way it will be very slow, see if we can optimize it, segregating it per phase/round already here.
        for stx in self.all_signalling_txes:
            stx.set_direct_successor(self.all_locking_txes)
        for stx in self.all_signalling_txes:
            stx.set_direct_successor(self.all_donation_txes)
        for ltx in self.all_locking_txes:
            ltx.set_direct_successor(self.all_locking_txes, reserve_mode=True)
        for ltx in self.all_locking_txes:
            ltx.set_direct_successor(self.all_donation_txes)
        for dtx in self.all_donation_txes:
            dtx.set_direct_successor(self.all_donation_txes, reserve_mode=True)

        all_tracked_txes = self.all_signalling_txes + self.all_locking_txes + self.all_donation_txes

        # MODIF: successors are now set per round (EXPERIMENTAL)
        """direct_successors = [ tx.direct_successor.txid for tx in all_tracked_txes if "direct_successor" in tx.__dict__ ]
        reserve_successors = [ tx.reserve_successor.txid for tx in all_tracked_txes if "reserve_successor" in tx.__dict__ ]
        selected_successors = direct_successors + reserve_successors"""

        if debug:
            for tx in all_tracked_txes:
                if "direct_successor" in tx.__dict__:
                    print("DONATION: Direct successor for", tx.txid, type(tx), tx.direct_successor.txid, type(tx.direct_successor))
                if "reserve_successor" in tx.__dict__:
                    print("DONATION: Reserve successor for", tx.txid, type(tx), tx.reserve_successor.txid, type(tx.reserve_successor))

        #if debug: print("All signalling txes:", self.all_signalling_txes)
        for rd in rounds[phase]:
            if rd == 4:
                self.available_slot_amount[rd] = self.req_amount - sum(self.effective_slots[:4])
            elif rd > 4:
                self.available_slot_amount[rd] = self.available_slot_amount[rd - 1] - self.effective_slots[rd - 1]
            elif rd > 0: # rounds 1, 2 and 3, 0 is already set
                self.available_slot_amount[rd] = self.available_slot_amount[rd - 1] - self.effective_locking_slots[rd - 1]
            # print("av. slot amount rd", rd, self.id, self.available_slot_amount[rd])

            # MODIF: selected successors now is segregated by round (EXPERIMENTAL!)
            # TODO: should be optimized (list of successors by round), so not the whole search has to be done in each rd.
            selected_successors = []
            for tx in all_tracked_txes:
                if self.validate_round(tx, rd):
                    if "direct_successor" in tx.__dict__:
                        selected_successors.append(tx.direct_successor.txid)
                if (type(tx) != SignallingTransaction) and (rd in (1, 2, 4, 5)) and (self.validate_round(tx, rd - 1)):
                    if "reserve_successor" in tx.__dict__:
                        selected_successors.append(tx.reserve_successor.txid)

            dstates[rd] = self._process_donation_states(rd, selected_successors, debug=debug, set_reward=set_reward, abandon_until=abandon_until)
            # if debug: print("Donation states of round", rd, ":", dstates[rd])

        if phase in (0, 1):

            self.donation_states = dstates
            self.processed[0] = True
            if phase == 0:
                self.processed[1] = True

        elif phase == 2:

            self.donation_states[4:] = dstates[4:]
            self.processed[1] = True

        self.total_donated_amount = sum(self.donated_amounts)
        if (phase in (0, 2)) and (self.dist_factor is not None):
            self.set_proposer_reward()
            self.processed[2] = True # complete # TODO after implementing the periods cleanly this is no longer necessary


    def _process_donation_states(self, rd, selected_successors, set_reward=False, abandon_until=0, debug=False):
        # This method always must run chronologically, with previous rounds already completed.
        # It can, however, be run to redefine phase 2 (rd 4-7).
        # It sets also the attributes that are necessary for the next round and its slot calculation.

        # 1. determinate the valid signalling txes (include reserve/locking txes).
        dstates = {}
        donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None
        round_stxes = [stx for stx in self.all_signalling_txes if self.get_stx_dist_round(stx) == rd]

        if debug: print("Checking signalling and reserve transactions of round", rd)
        if rd in (0, 3, 6, 7):

             valid_stxes = self._validate_basic(round_stxes, rd, selected_successors, reserve_mode=False, debug=debug)
             valid_rtxes = [] # No RTXes in these rounds.
             total_reserved_amount = 0
        else:
             # base_txes are the potential reserve transactions
             if rd in (1, 2):
                 base_txes = self.locking_txes[rd - 1]
             elif rd == 4:
                 base_txes = [t for rd in self.donation_txes[:4] for t in rd]
             else:
                 base_txes = self.donation_txes[rd - 1]

             # NOTE: additional sorting here was kept as there were slight inconsistencies otherwise
             raw_round_rtxes = sorted(base_txes, key = lambda x: (x.blockheight, x.blockseq))
             round_rtxes = self._validate_basic(raw_round_rtxes, rd, selected_successors, debug=debug, reserve_mode=True)

             #round_rtxes = [rtx for rtx in raw_round_rtxes if (rtx.reserved_amount) and (self.check_donor_address(rtx, rd, rtx.reserve_address, add_address=True, debug=debug, reserve=True))]
             if debug: print("DONATION: All possible reserve TXes in round:", rd, ":", [(t.txid, t.reserved_amount) for t in round_rtxes])

             # Reserve Transactions are validated first, as they have higher priority.
             valid_rtxes = self._validate_priority(round_rtxes, rd, selected_successors, reserve_mode=True, debug=debug) if len(round_rtxes) > 0 else []
             total_reserved_amount = sum([tx.reserved_amount for tx in valid_rtxes])

             # If the reserved amount exceeds the total available slots, do not process signalling transactions,
             # so slots of 0 are avoided.
             if debug: print("DONATION: Total reserved in round {}: {} - Available slot amount: {}".format(rd, total_reserved_amount, self.available_slot_amount[rd]))

             if total_reserved_amount > self.available_slot_amount[rd]:
                 # MODIFIED: we need to delete the successors here too
                 for stx in round_stxes:
                     if "direct_successor" in stx.__dict__:
                         self._delete_invalid_successor(stx.direct_successor, selected_successors)
                 valid_stxes = []
             else:
                 valid_stxes = self._validate_priority(round_stxes, rd, selected_successors, debug=debug) if len(round_stxes) > 0 else []

        if debug: print("DONATION: Valid Signalling TXes in round:", rd, ":", [(t.txid, t.amount) for t in valid_stxes])
        if debug: print("DONATION: Valid Reserve TXes in round:", rd, ":", [(t.txid, t.reserved_amount) for t in valid_rtxes])

        # 2. Calculate total signalled amount and set other variables.

        self.reserve_txes[rd] = valid_rtxes
        self.reserved_amounts[rd] = total_reserved_amount
        self.signalling_txes[rd] = valid_stxes
        self.signalled_amounts[rd] = sum([tx.amount for tx in valid_stxes])
        self.effective_slots[rd] = 0
        self.donated_amounts[rd] = 0

        if rd < 4:
            self.locked_amounts[rd] = 0
            self.effective_locking_slots[rd] = 0

        # 3. Generate DonationState and add locking/donation txes:
        # TODO maybe this could go into DonationState.init()

        # sort origin transactions, as they're here not in chronologic order due to be of 2 distinct types.
        all_origin_txes = sorted(valid_stxes + valid_rtxes, key = lambda x: (x.blockheight, x.blockseq))

        for tx in all_origin_txes:

            donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None
            state = "incomplete"
            # Initial slot: based on signalled amount.
            slot = self.get_slot(tx, rd, debug=debug)
            if debug: print("SLOT: Slot for tx", tx.txid, ":", slot)
            if slot == 0:
                if debug: print("SLOT: Donation state without positive slot not created.")
                try:
                   if tx.direct_successor.txid in selected_successors:
                       self._delete_invalid_successor(tx.direct_successor, selected_successors)
                except AttributeError:
                   pass
                continue

            if rd < 4:
                locking_tx = self._get_ttx_successor(rd, tx, self.all_locking_txes, selected_successors, debug=debug, mode="origin")

                # If the timelock is not correct, locking_tx is not added, and no donation tx is taken into account.
                # The DonationState will be incomplete in this case. Only the SignallingTx is being added.
                # if debug and locking_tx is not None: print("TX", tx.txid, "Locking tx:", locking_tx.txid, type(locking_tx))
                if (locking_tx is not None) and self.validate_timelock(locking_tx):

                    # TODO is this really the most efficient way?
                    ltxes = deepcopy(self.locking_txes)
                    ltxes[rd].append(locking_tx)
                    self.locking_txes = ltxes

                    self.locked_amounts[rd] += locking_tx.amount
                    effective_locking_slot = min(slot, locking_tx.amount)

                    # TODO: do we need to priorize direct successors here too?
                    if debug: print("DONATION: Lookup Successor for locking tx:", locking_tx.txid)
                    donation_tx = self._get_ttx_successor(rd, locking_tx, self.all_donation_txes, selected_successors, debug=debug)
                    if debug and donation_tx: print("DONATION: Donation tx added in locking mode", donation_tx.txid, rd)

            else:
                if debug: print("DONATION: Lookup Successor for reserve/signalling tx:", tx.txid)
                # donation_tx = tx.get_output_tx(sorted_dtxes, self, rd, debug=debug)
                donation_tx = self._get_ttx_successor(rd, tx, self.all_donation_txes, selected_successors, debug=debug, mode="origin")
                if debug and donation_tx: print("DONATION: Donation tx added in donation mode", donation_tx.txid, rd)

            if donation_tx:
                if rd < 4:
                    effective_slot = min(effective_locking_slot, donation_tx.amount)

                else:
                    effective_slot = min(slot, donation_tx.amount)

                self.donation_txes[rd].append(donation_tx)
                self.donated_amounts[rd] += donation_tx.amount
                state = "complete" if (effective_slot > 0) else "abandoned"

            elif (abandon_until >= rd):
                if rd < 4:
                    # if we're already past round 3, then also states with missing donation release tx are abandoned
                    if (locking_tx is None) or ((donation_tx is None) and (abandon_until >= 4)):
                        state = "abandoned"
                else:
                   state = "abandoned"

            # In round 1-4, the effectively locked slot amounts are the values which determinate the
            # slot rest for the next round. In round 5-8 it's the Donation effective slots.
            if effective_locking_slot and (rd < 4):
                self.effective_locking_slots[rd] += effective_locking_slot
            if effective_slot:
                self.effective_slots[rd] += effective_slot

            if type(tx) == SignallingTransaction:
                signalling_tx = tx
                reserve_tx = None
            elif type(tx) in (LockingTransaction, DonationTransaction):
                reserve_tx = tx
                signalling_tx = None
            else:
                continue

            dstate = DonationState(signalling_tx=signalling_tx, reserve_tx=reserve_tx, locking_tx=locking_tx, donation_tx=donation_tx, slot=slot, effective_slot=effective_slot, effective_locking_slot=effective_locking_slot, dist_round=rd, state=state)

            if set_reward:
                dstate.set_reward(self)

            dstates.update({dstate.id : dstate})

        return dstates

    def _delete_invalid_successor(self, successor_tx, selected_successors):
        if successor_tx is None:
            return
        txid = successor_tx.txid
        #print("checking", txid)
        if txid in selected_successors:
            #print("found.")
            txid_index = selected_successors.index(txid)
            # second level: if locking tx is deleted, donation tx must also be deleted.
            if type(successor_tx) == LockingTransaction:
                for successor_attr in ("direct_successor", "reserve_successor"):
                    try:
                        l2_successor = successor_tx.__dict__[successor_attr]
                    except KeyError:
                        continue

                    # print("l2 txid", l2_successor.txid)
                    if l2_successor.txid in selected_successors:
                        # print("deleting", l2_successor.txid)
                        l2_txid_index = selected_successors.index(l2_successor.txid)
                        del selected_successors[l2_txid_index]

            del selected_successors[txid_index]

    def _validate_basic(self, tx_list, rd, selected_successors, reserve_mode=False, debug=False, add_address=True):
        # basic validation steps: donor address duplication, reserve address existence, proposer identity.
        result = []

        for tx in tx_list:
            if reserve_mode:
                successor_tx = tx.reserve_successor if "reserve_successor" in tx.__dict__ else None
                address = tx.reserve_address
                if not tx.reserved_amount:
                    if debug: print("DONATION: Potential reserve transaction", tx.txid, "rejected, no reserved amount.")
                    continue
            else:
                successor_tx = tx.direct_successor if "direct_successor" in tx.__dict__ else None
                address = tx.address

            # Proposers cannot be donors
            if address == self.donation_address:
                if debug: print("DONATION: Proposer {} trying to donate, this is invalid. No donation state created.".format(address))
                if successor_tx is not None:
                    self._delete_invalid_successor(successor_tx, selected_successors)
                continue

            if self.check_donor_address(tx, rd, address, add_address=add_address, reserve=reserve_mode, debug=debug):
                result.append(tx)

            elif successor_tx is not None:
                self._delete_invalid_successor(successor_tx, selected_successors)

        return result

    def _get_ttx_successor(self, rd: int, tx: TrackedTransaction, potential_successors: list, selected_successors: list, mode: str=None, debug: bool=False) -> TrackedTransaction:
        # used: we need to ensure there are no duplicates
        # used_txids = [t.txid for rd in used for t in rd] if used is not None else []
        try:
            if mode == "origin" and type(tx) != SignallingTransaction:
                reserve_mode = True
                # origin mode: we test for the reserve successor if we are checking a reserve transaction
                selected_tx = tx.reserve_successor
            else:
                reserve_mode = False
                selected_tx = tx.direct_successor
            # selected_tx = selected_successors[tx.txid]
        except AttributeError: # successor still not existing
            # reserve_mode = False if type(tx) == SignallingTransaction else True
            indirect_successors = tx.get_indirect_successors(potential_successors, reserve_mode=reserve_mode)
            if debug: print("DONATION: Indirect Successors of tx", tx.txid, ":" ,[t.txid for t in indirect_successors])
            for suc_tx in indirect_successors:
                if (suc_tx.txid not in selected_successors) and (self.validate_round(suc_tx, rd)):
                # if suc_tx not in selected_successors.values() and (self.validate_round(suc_tx, rd)):
                    selected_tx = suc_tx
                    selected_successors.append(selected_tx.txid)
                    break

                elif debug:
                    if suc_tx.txid in selected_successors:
                        print("DONATION: Successor", suc_tx.txid, "rejected: is already a successor of a valid earlier transaction.")
                    if not self.validate_round(suc_tx, rd):
                        print("DONATION: Successor", suc_tx.txid, "rejected: blockheight out of round", rd)
            else:
                selected_tx = None


        return selected_tx

    def check_donor_address(self, tx, rd, addr, reserve=False, add_address=False, debug=False):
        # checks if a donor address of a transaction was already used in the same phase for the same tx type.
        # Donor address can be found by the preceding phase (for reserve txes).
        # add_address is needed because there are cases where the addition occurs later.
        # NOTES from tx.get_output_tx():
        # You must be able to use the same donor address in phase 1 and 2,
        # due to the reserve transaction question in rd. 4/5. => TODO: is this still true with unique donor addresses?
        # TODO: Can this be improved? adr, type(tx), phase should give the same value for many
        # txes of the list, so "continue" isn't the best option.
        phase = rd // 4
        if debug: print("DONATION: Checking tx", tx.txid, "with address", tx.address)

        # tx_type = "reserve" if reserve else type(tx)
        tx_type = "signalling" if reserve else tx.ttx_type
        if (addr, tx_type, phase) in self.donor_addresses:

            if debug: print("DONATION: TX {} rejected, donor address {} already used in this phase for type {}.".format(tx.txid, addr, tx_type))
            return False

        else:

            if add_address:
                self.add_donor_address(addr, tx_type, phase, reserve=reserve)
            return True

    def add_donor_address(self, addr, tx_type, phase, reserve=False):
        if reserve:
            tx_type = "signalling"
        self.donor_addresses.append((addr, tx_type, phase))

    def get_stx_dist_round(self, stx):
        # checks block height of signalling transaction, and returns round.
       for rd in range(8):
           start = self.rounds[rd][0][0]
           end = self.rounds[rd][1][0]

           if start <= stx.blockheight <= end:
               # print("Start/bh/end:", start, stx.blockheight, end, "txid:", stx.txid)
               return rd
       else:
           # raise InvalidTrackedTransactionError("Incorrect blockheight for a signalling transaction.")
           return None

    def set_dist_factor(self, ending_proposals):
        # TODO: It could make sense to calculate the rewards here directly, i.e. multiply this with deck.epoch_quantity
        # Proposal factor: if there is more than one proposal ending in the same epoch,
        # the resulting slot is divided by the req_amounts of them.

        if len(ending_proposals) > 1:
            total_req_amount = sum([p.req_amount for p in ending_proposals])
            self.dist_factor = Decimal(self.req_amount) / total_req_amount
        else:
            self.dist_factor = Decimal(1)

    def set_proposer_reward(self):
        filled_amount = sum(self.effective_slots)

        if filled_amount >= self.req_amount:
            proposer_proportion = 0
        else:
            proposer_proportion = Decimal((self.req_amount - filled_amount) / self.req_amount)
        if proposer_proportion > 0:
            reward_units = self.deck.epoch_quantity * (10 ** self.deck.number_of_decimals)
            self.proposer_reward = int(proposer_proportion * self.dist_factor * reward_units)
        else:
            self.proposer_reward = 0

    def _validate_priority(self, tx_list: list, dist_round: int, selected_successors: list, reserve_mode: bool=False, debug: bool=False):
        """Validates the priority of signalling and reserve transactions in round 2, 3, 5 and 6."""
        # New version with DonationStates, modified to validate a whole round list at once (more efficient).
        # Should be optimized in the beta/release version.
        # The type test seems ugly but is necessary unfortunately. All txes given to this method have to be of the same type.
        valid_txes = []

        # Slots are considered filled if 95% of the initial slot are locked or donated.
        # This prevents small rounding errors and P2TH/tx fees to make the slot invalid for the next rounds.
        # 95% allows a donation of 1 coin minus 0.04 fees, without having to add new UTXOs.
        fill_threshold = Decimal(0.95)

        if dist_round in (0, 3, 6, 7):
            # TODO: this should never be called in these rounds so for now we raise a ValueError.
            # In rounds without priority check, we only need to check that donor addresses are not re-used.
            raise ValueError("Round {} is not a priority round.".format(rd))

        elif dist_round == 4: # rd 5 is special because all donors of previous rounds are admitted.

            valid_dstates = [dstate for rd in (0, 1, 2, 3) for dstate in self.donation_states[rd].values()]

            if type(tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates if dstate.donation_tx is not None]

        elif dist_round == 5:

            valid_dstates = [dstate for dstate in self.donation_states[4].values()]

            if type(tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates if dstate.donation_tx is not None]

        elif dist_round in (1, 2):

            valid_dstates = [dstate for dstate in self.donation_states[dist_round - 1].values()]
            if type(tx_list[0]) == LockingTransaction:
                try:
                    valid_rtx_txids = [dstate.locking_tx.txid for dstate in valid_dstates if dstate.locking_tx is not None]
                except AttributeError as e:
                    return []

        # Locking or DonationTransactions: we simply look for the DonationState including it
        # If it's not in any of the valid states, it can't be valid.

        for tx in tx_list:
            # successor:
            try:
                if reserve_mode:
                    #successor_txid = tx.reserve_successor.txid
                    successor_tx = tx.reserve_successor
                else:
                    #successor_txid = tx.direct_successor.txid
                    successor_tx = tx.direct_successor
            except AttributeError:
                #successor_txid = None
                successor_tx = None

            if debug: print("Checking tx:", tx.txid, type(tx))
            if type(tx) in (LockingTransaction, DonationTransaction):

                for dstate in valid_dstates:
                    if (dstate.locking_tx is not None) and (dstate.locking_tx.txid == tx.txid):
                        break
                    elif (dstate.donation_tx is not None) and (dstate.donation_tx.txid == tx.txid):
                        break
                else:
                    if debug: print("Transaction rejected by priority check:", tx.txid)
                    # self._delete_invalid_successor(successor_txid, selected_successors)
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue
                parent_dstate = dstate

            # In the case of signalling transactions, we must look for donation/locking TXes
            # using the spending address as donor address, because the used output can be another one.
            elif type(tx) == SignallingTransaction:

                # Donor address check is done first, but without adding addresses; we do this at the end of validation.
                # We don't check donor addresses for Locking/Donation txes, they are checked in tx.get_output_addresses().
                if not self.check_donor_address(tx, dist_round, tx.address, add_address=False, debug=debug):
                    # self._delete_invalid_successor(successor_txid, selected_successors)
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue
                for dstate in valid_dstates:
                    #if debug: print("Donation state checked:", dstate.id, "for tx", tx.txid, "with input addresses", tx.input_addresses)
                    if dstate.donor_address in tx.input_addresses:

                        parent_dstate = dstate
                        self.add_donor_address(tx.address, tx.ttx_type, (dist_round // 4))
                        break
                else:
                    if debug: print("Transaction rejected by priority check:", tx.txid)
                    # self._delete_invalid_successor(successor_txid, selected_successors)
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue

            try:
                # if debug: print("TX DSTATE", tx_dstate.id, "for", tx.txid)
                if (dist_round < 4) and (parent_dstate.locking_tx.amount >= (Decimal(parent_dstate.slot) * fill_threshold)): # we could use the "complete" attribute? or only in the case of DonationTXes?
                    valid_txes.append(tx)
                    parent_dstate.child_state_ids.append(tx.txid)
                elif (dist_round >= 4) and (parent_dstate.donation_tx.amount >= (Decimal(parent_dstate.slot) * fill_threshold)):
                    valid_txes.append(tx)
                    parent_dstate.child_state_ids.append(tx.txid)

                else:
                    if debug: print("Reserve transaction rejected due to incomplete slot of parent donation state:", tx.txid, "\nSlot:", parent_dstate.slot, "Effective Slot (donated amount): {} Locking Slot: {}".format(parent_dstate.effective_slot, parent_dstate.effective_locking_slot))
                    # self._delete_invalid_successor(successor_txid, selected_successors)
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue
            except AttributeError as e:
                if debug: print("Required transaction (donation or locking) of parent donation state missing:", tx.txid)
                if debug: print(e)
                continue

        return valid_txes

    def validate_timelock(self, ltx):
        """Checks that the timelock of the donation is correct."""

        # Timelock must be set at least to the block height of the start of the end epoch.
        # We take the value of the first ProposalTransaction here, because in the case of Proposal Modifications,
        # all LockedTransactions need to stay valid.

        original_phase2_start = (self.start_epoch + self.first_ptx.epoch_number) * self.deck.epoch_length

        if ltx.timelock >= original_phase2_start:
            return True
        else:
            return False

    def validate_round(self, tx: TrackedTransaction, dist_round: int) -> bool:
        # checks a transaction for correct round.
        # formerly in TrackedTransaction.get_output_tx.
        if type(tx) == DonationTransaction and dist_round < 4: # replaced "locking mode"
            startblock = self.release_period[0]
            endblock = self.release_period[1]
        else:
            startblock = self.rounds[dist_round][1][0]
            endblock = self.rounds[dist_round][1][1] # last valid block

        if (startblock <= tx.blockheight <= endblock):
            return True
        else:
            return False

    def get_slot(self, tx: TrackedTransaction, dist_round: int, debug: bool=False) -> int:

        # Check transaction type (signalling or donation/locking):
        # This works because SignallingTransactions have no attribute .reserved_amount and thus throw AttributeError.
        try:
            tx_amount = tx.reserved_amount
            if dist_round in (0, 3, 6, 7): # Reserve transactions are not valid in these rounds.
                raise ValueError("No reserve transactions in this round.")
        except AttributeError:
            tx_amount = tx.amount

        # First 4 rounds require timelocks, so ProposalState.locked_amounts must be initalized.
        # TODO: check if this is really necessary
        if dist_round in (0, 1, 2, 3) and (self.locked_amounts is None):
            self.locked_amounts = [0, 0, 0, 0]

        if dist_round in (0, 6):
            # Note: available_amount[0] is the same than req_amount.
            return get_raw_slot(tx_amount, self.available_slot_amount[dist_round], total_amount=self.signalled_amounts[dist_round])

        elif dist_round in (1, 2, 4, 5):
            # in priority rounds, we need to check if the signalled amounts correspond to a donation in the previous round
            # These are added to the reserved amounts (second output of DonationTransactions).
            return get_priority_slot(tx, rtxes=self.reserve_txes[dist_round], stxes=self.signalling_txes[dist_round], av_amount=self.available_slot_amount[dist_round], ramount=self.reserved_amounts[dist_round], samount=self.signalled_amounts[dist_round], debug=debug)

        elif dist_round in (3, 7):
            return get_first_serve_slot(tx, self.signalling_txes[dist_round], slot_rest=self.available_slot_amount[dist_round])

        else:
            return 0 # if dist_round is incorrect

class DonationState(object):
    # A DonationState contains Signalling, Locked and Donation transaction and the slot.
    # Must be created always with either SignallingTX or ReserveTX.
    # Child_state_id allows more control over inheriting. A parent state would be even better but would need refactoring or costly processing.

    def __init__(self, signalling_tx=None, reserve_tx=None, locking_tx=None, donation_tx=None, slot=None, dist_round=None, effective_slot=None, effective_locking_slot=None, reward=None, state="incomplete"):
        self.signalling_tx = signalling_tx
        self.reserve_tx = reserve_tx
        self.locking_tx = locking_tx
        self.donation_tx = donation_tx
        self.donated_amount = donation_tx.amount if self.donation_tx else 0
        self.dist_round = dist_round
        self.slot = slot
        self.effective_slot = effective_slot
        self.effective_locking_slot = effective_locking_slot
        self.reward = reward
        self.state = state
        self.child_state_ids = [] # this will only be filled if there are child states

        if signalling_tx is not None:
            self.origin_tx = signalling_tx
            self.donor_address = self.origin_tx.address
            self.signalled_amount = self.origin_tx.amount
        elif reserve_tx is not None:
            self.origin_tx = reserve_tx
            self.donor_address = self.origin_tx.reserve_address
            self.signalled_amount = self.origin_tx.reserved_amount
        else:
            raise InvalidDonationStateError("A DonationState must be initialized with a signalling or reserve address.")


        self.id = self.origin_tx.txid

    def set_reward(self, proposal_state):
        if (self.effective_slot is not None) and (self.effective_slot > 0):
            slot_proportion = Decimal(self.effective_slot) / proposal_state.req_amount
            reward_units = proposal_state.deck.epoch_quantity * (10 ** proposal_state.deck.number_of_decimals)
            self.reward = int(slot_proportion * reward_units * proposal_state.dist_factor)


class InvalidDonationStateError(ValueError):
    # raised anytime when a DonationState is not following the intended format.
    pass

