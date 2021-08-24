from pypeerassets.at.dt_slots import get_slot
from pypeerassets.at.dt_entities import SignallingTransaction, DonationTransaction, LockingTransaction
from decimal import Decimal
from copy import deepcopy

# TODO: optimize the initialization to make deepcopy innecessary.
# TODO: Locked amounts does not work. (solved at 1/05?)

def linit():
    return deepcopy([[],[],[],[],[],[],[],[]])
def linitz():
    return deepcopy([0, 0, 0, 0, 0, 0, 0, 0])
def linitz4():
    return deepcopy([0, 0, 0, 0])

class ProposalState(object):
   # A ProposalState unifies all functions from proposals which are mutable.
   # i.e. which can change after the first proposal transaction was sent.

    def __init__(self, valid_ptx, first_ptx, rounds=[], signalling_txes=linit(), locking_txes=linit(), donation_txes=linit(), signalled_amounts=linitz(), locked_amounts=linitz(), donated_amounts=linitz(), reserve_txes=linit(), reserved_amounts=linitz(), effective_slots=linitz(), effective_locking_slots=linitz4(), available_slot_amount=None, donation_states=[], total_donated_amount=None, provider=None, current_blockheight=None, all_signalling_txes=[], all_donation_txes=[], all_locking_txes=[], all_voting_txes=[], donor_addresses=[], initial_votes=None, final_votes=None, voting_states=[[],[]], voting_txes=[[],[]], dist_factor=None, processed=None, proposer_reward=None):

        self.first_ptx = first_ptx # First ProposalTransaction of the ProposalState..
        self.valid_ptx = valid_ptx # Last proposal transaction which is valid.

        self.req_amount = self.valid_ptx.req_amount # should work with ProposalModifications due to side effect
        self.id = self.first_ptx.txid # Identification. Does not change with Modifications.

        # The round length of the second phase (not the first one) can be changed in ProposalModifications.
        # Thus all values based on round_length have 2 values, for the first and the second phase.
        self.round_lengths = [self.first_ptx.round_length, self.valid_ptx.round_length] # should work with ProposalModifications due to side effect
        self.donation_address = self.first_ptx.donation_address
        self.deck = self.first_ptx.deck
        self.donor_addresses = donor_addresses

        # Slot Allocation Round Attributes are lists with values for each of the 8 distribution rounds
        # Phase 2 can vary if there is a ProposalModification, so this can be set various times.
        if not rounds:
            self.set_rounds(phase=0)
        else:
            self.rounds = rounds
            self.dist_start = dist_start # start block of first voting/distribution round.

        if not current_blockheight and (not signalling_txes or not donation_txes):
            current_blockheight = provider.getblockcount()

        # New: Attributes for all TrackedTransactions without checking them (with the exception of VotingTransactions)
        self.all_signalling_txes = all_signalling_txes
        self.all_locking_txes = all_locking_txes
        self.all_donation_txes = all_donation_txes
        self.all_voting_txes = all_voting_txes

        # The following attributes are set by the parser once a proposal ends.
        # Only valid transactions are recorded in them.
        self.signalling_txes = signalling_txes
        self.signalled_amounts = signalled_amounts
        self.locking_txes = locking_txes
        self.locked_amounts = locked_amounts
        self.donation_txes = donation_txes
        self.donated_amounts = donated_amounts
        self.donation_states = donation_states
        self.total_donated_amount = total_donated_amount
        self.reserve_txes = reserve_txes
        self.reserved_amounts = reserved_amounts

        # Votes are set after the start and the end phase.
        self.voting_txes = voting_txes
        self.initial_votes = initial_votes
        self.final_votes = final_votes
        # EXPERIMENTAL: Voting states with balances
        # Is a list of 2 lists (initial/final)
        # self.voting_states = voting_states # replaced by self.voting_txes

        # The effective slot values are the sums of the effective slots in each round.
        self.effective_locking_slots = effective_locking_slots
        self.effective_slots = effective_slots
        # Available slot amount: part of the req_amount which is still available for slots.
        self.available_slot_amount = available_slot_amount

        # State: The general state of the proposal. Can be "active", "complete" or "abandoned".
        # At the start until the first voting round it is set to active.
        self.state = "active"

        # Factor to be multiplied with token amounts, between 0 and 1.
        # It depends on the Token Quantity per distribution period
        # and the number of coins required by the proposals in their ending period.
        # The higher the amount of proposals and their required amounts, the lower this factor is.
        self.dist_factor = dist_factor
        # Processed is a list of 3 values and refers to the donation states processed in each of both phases and the
        # completeness (i.e. if there were blocks missing for the last processed phase):
        # [ phase1, phase2, complete ]
        if not processed:
            self.processed = [False, False, False] # TODO: delete third one, no longer needed!
        else:
            self.processed = processed

        # If there are slots missing at the end, the proposer can claim the proportion.
        self.proposer_reward = proposer_reward


    def set_rounds(self, phase=0):
        # This method sets the start and end blocks of all rounds and periods of either the first or the second phase.
        # Phase 0 means: both phases are calculated.
        # Method is only called once per phase or when a proposal has been modified.

        # 1. Calculate round starts
        epoch_length = self.deck.epoch_length

        round_starts = [None] * 8 # all changed from 9 to 8
        round_halfway = [None] * 8
        self.rounds = [None] * 8
        self.security_periods = [None] * 2
        self.voting_periods = [None] * 2
        security_period_lengths = [max(l // 2, 2) for l in self.round_lengths] # minimum 2 blocks
        voting_period_lengths = [l * 4 for l in self.round_lengths]
        release_period_length = voting_period_lengths[0]

        # halfway = self.first_ptx.round_length // 2 # modified: this would lead to problems when only the second phase is processed.
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
            self.security_periods[0] = [self.dist_start, self.dist_start + security_period_lengths[0]]
            voting_p1_start = self.security_periods[0][1] + 1
            self.voting_periods[0] = [voting_p1_start, voting_p1_start + voting_period_lengths[0]]

            phase_start = self.dist_start + pre_allocation_period_phase1

            for rd in range(4): # first phase has 4 rounds
                round_starts[rd] = phase_start + self.round_lengths[0] * rd
                round_halfway[rd] = round_starts[rd] + halfways[0] # MODIF: instead of "halfway"
                self.rounds[rd] = [[round_starts[rd], round_halfway[rd] - 1], [round_halfway[rd], round_starts[rd] + self.round_lengths[0] - 1]]

        if phase in (0, 2):
            # we use valid_ptx here, this gives the option to change the round length of 2nd round.

            # epoch = self.end_epoch # final vote/distribution should always begin at the start of the end epoch.

            # End epoch is 1 after last working epoch.
            self.end_epoch = self.start_epoch + self.valid_ptx.epoch_number + 1
            end_epoch_start = self.end_epoch * epoch_length
            phase_start = self.end_epoch * epoch_length + pre_allocation_period_phase2

            self.security_periods[1] = [end_epoch_start, end_epoch_start + security_period_lengths[1]]
            voting_p2_start = self.security_periods[1][1] + 1
            self.voting_periods[1] = [voting_p2_start, voting_p2_start + voting_period_lengths[1]]

            release_start = self.voting_periods[1][1] + 1
            self.release_period = [release_start, release_start + release_period_length]

            for i in range(4): # second phase has 4 rounds
                # MODIFIED: no longer 5 rounds, but 4, because proposer round is innecesary.
                rd = i + 4
                round_starts[rd] = phase_start + self.round_lengths[1] * i
                round_halfway[rd] = round_starts[rd] + halfways[1] # MODIF: instead of "halfway"
                self.rounds[rd] = [[round_starts[rd], round_halfway[rd] - 1], [round_halfway[rd], round_starts[rd] + self.round_lengths[1] - 1]]

    def modify(self):
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

    def set_donation_states(self, phase=0, current_blockheight=None, debug=False):
        # Phase 0 means both phases are calculated.

        # If rounds are not set, or phase is 2 (re-defining of the second phase), then we set it.
        if len(self.rounds) == 0 or (phase == 2):
            if debug: print("Setting rounds for proposal:", self.id)
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
        #if debug: print("All signalling txes:", self.all_signalling_txes)
        for rd in rounds[phase]:
            if rd == 4:
                self.available_slot_amount[rd] = self.req_amount - sum(self.effective_slots[:4])
            elif rd > 4:
                self.available_slot_amount[rd] = self.available_slot_amount[rd - 1] - self.effective_slots[rd - 1]
            elif rd > 0: # rounds 1, 2 and 3, 0 is already set
                self.available_slot_amount[rd] = self.available_slot_amount[rd - 1] - self.effective_locking_slots[rd - 1]
            # print("av. slot amount rd", rd, self.id, self.available_slot_amount[rd])

            dstates[rd] = self._process_donation_states(rd, debug=debug, set_reward=set_reward, abandon_until=abandon_until)
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


    def _process_donation_states(self, rd, set_reward=False, abandon_until=0, debug=False):
        # This function always must run chronologically, with previous rounds already completed.
        # It can, however, be run to redefine phase 2 (rd 4-7).
        # It sets also the attributes that are necessary for the next round and its slot calculation.

        # 1. determinate the valid signalling txes (include reserve/locking txes).
        dstates = {}
        donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None

        all_stxes = []

        for stx in self.all_signalling_txes:
            # if debug: print("STX round:", self.get_stx_dist_round(stx), "Current round:", rd)
            if self.get_stx_dist_round(stx) == rd:
                all_stxes.append(stx)
                if debug: print("STX", stx.txid, "appended in round", rd)

        # if debug: print("All signalling txes for round", rd, ":", all_stxes)
        if rd in (0, 3, 6, 7):
             # first round, round 6 and first-come-first-serve rds: all signalling txes inside the blockheight limit.
             valid_stxes = all_stxes
             valid_rtxes = [] # No RTXes in these rounds.
        else:
             # TODO: Could be made more efficient, if necessary.
             if rd in (1, 2):
                 base_txes = self.locking_txes[rd - 1]
             elif rd == 4:
                 base_txes = [t for rd in self.donation_txes[:4] for t in rd]
             else:
                 base_txes = self.donation_txes[rd - 1]

             all_rtxes = [tx for tx in base_txes if (tx.reserved_amount is not None) and (tx.reserved_amount > 0)]
             if debug: print("All possible reserve TXes in round:", rd, ":", [(t.txid, t.reserved_amount) for t in all_rtxes])

             valid_stxes = self.validate_priority(all_stxes, rd, debug=debug) if len(all_stxes) > 0 else []
             valid_rtxes = self.validate_priority(all_rtxes, rd, debug=debug) if len(all_rtxes) > 0 else []

        if debug: print("Valid Signalling TXes in round:", rd, ":", [(t.txid, t.amount) for t in valid_stxes])
        if debug: print("Valid Reserve TXes in round:", rd, ":", [(t.txid, t.reserved_amount) for t in valid_rtxes])

        # 2. Calculate total signalled amount and set other variables.

        self.signalling_txes[rd] = valid_stxes
        self.signalled_amounts[rd] = sum([tx.amount for tx in valid_stxes])
        self.reserve_txes[rd] = valid_rtxes
        self.reserved_amounts[rd] = sum([tx.reserved_amount for tx in valid_rtxes])
        self.effective_slots[rd] = 0
        self.donated_amounts[rd] = 0

        if rd < 4:
            self.locked_amounts[rd] = 0
            self.effective_locking_slots[rd] = 0

        # 3. Generate DonationState and add locking/donation txes:
        # TODO: Do we need to validate the correct round of locking/donation, and even reserve txes?
        for tx in (valid_stxes + valid_rtxes):
            donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None
            state = "incomplete"
            # Initial slot: based on signalled amount.
            # TODO: if we can give "self" simply to get_slot, we could make this simpler.
            # Maybe refactor it as a method of ProposalState.
            # MODIFIED: first_req_amount and final_req_amount removed as no longer necessary.
            # reserve_txes and available_amount added.
            slot = get_slot(tx,
                            rd,
                            signalling_txes=self.signalling_txes,
                            locking_txes=self.locking_txes,
                            donation_txes=self.donation_txes,
                            reserve_txes=self.reserve_txes,
                            signalled_amounts=self.signalled_amounts,
                            reserved_amounts=self.reserved_amounts,
                            locked_amounts=self.locked_amounts,
                            donated_amounts=self.donated_amounts,
                            effective_slots=self.effective_slots,
                            effective_locking_slots=self.effective_locking_slots,
                            available_amount=self.available_slot_amount)
            if debug: print("Slot for tx", tx.txid, ":", slot)
            if rd < 4:
                locking_tx = tx.get_output_tx(self.all_locking_txes, self, rd)
                # If the timelock is not correct, locking_tx is not added, and no donation tx is taken into account.
                # The DonationState will be incomplete in this case. Only the SignallingTx is being added.
                if (locking_tx is not None) and self.validate_timelock(locking_tx):
                    #print("locking txes before", [t.txid for rd in self.locking_txes for t in rd])
                    ltxes = deepcopy(self.locking_txes)
                    ltxes[rd].append(locking_tx)
                    self.locking_txes = ltxes
                    # print("adding locking tx", locking_tx.txid, "in round", rd)
                    #print("locking_txes after", [t.txid for rd in self.locking_txes for t in rd])
                    # TODO: There are amounts at round 4 which should not be there. => Re-check if solved!
                    self.locked_amounts[rd] += locking_tx.amount
                    effective_locking_slot = min(slot, locking_tx.amount)
                    # print("EFFECTIVE LOCKING SLOT RD", rd, effective_locking_slot, slot, locking_tx.amount, locking_tx.txid, self.locked_amounts)
                    # print("Searching child txes of locking tx", locking_tx.txid)
                    donation_tx = locking_tx.get_output_tx(self.all_donation_txes, self, rd, mode="locking")
                    if debug and donation_tx: print("Donation tx added in locking mode", donation_tx.txid, rd)
                    # if donation_tx: print("Donation tx added in locking mode", donation_tx.txid, rd)

            else:
                # print("Searching child txes of tx", tx.txid, "of type", type(tx))
                donation_tx = tx.get_output_tx(self.all_donation_txes, self, rd)
                if debug and donation_tx: print("Donation tx added in donation mode", donation_tx.txid, rd)

            if donation_tx:
                if rd < 4:
                    effective_slot = min(effective_locking_slot, donation_tx.amount)

                else:
                    effective_slot = min(slot, donation_tx.amount)

                self.donation_txes[rd].append(donation_tx)
                self.donated_amounts[rd] += donation_tx.amount
                state = "complete" if (effective_slot > 0) else "abandoned"

            elif (abandon_until >= rd):
                if rd <= 3:
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

    def get_stx_dist_round(self, stx):
        # This one only checks for the blockheight. Thus it can only be used for stxes.
       for rd in range(8):
           start = self.rounds[rd][0][0]
           end = self.rounds[rd][1][0]
           # old version:
           # start = self.round_starts[rd]
           # end = self.round_halfway[rd] - 1

           # print("Start/bh/end:", start, stx.blockheight, end, "txid:", stx.txid)
           if start <= stx.blockheight <= end:
               return rd
       else:
           # raise InvalidTrackedTransactionError("Incorrect blockheight for a signalling transaction.")
           return None

    def set_dist_factor(self, ending_proposals):
        # TODO: It could make sense to calculate the rewards here directly, i.e. multiply this with deck.epoch_quantity
        # Proposal factor: if there is more than one proposal ending in the same epoch,
        # the resulting slot is divided by the req_amounts of them.
        # This is set in the function dt_parser_utils.get_valid_ending_proposals.

        # ending_proposals = [p for p in pst.valid_proposals.values() if p.end_epoch == proposal_state.end_epoch]

        # print("Ending proposals in the same epoch than the one referenced here:", ending_proposals)

        if len(ending_proposals) > 1:
            total_req_amount = sum([p.req_amount for p in ending_proposals])
            self.dist_factor = Decimal(self.req_amount) / total_req_amount
        else:
            self.dist_factor = Decimal(1)

        # print("Dist factor", self.dist_factor)

    def set_proposer_reward(self):
        # MODIFIED. Based on effective slots.
        filled_amount = sum(self.effective_slots)
        # Alternative:
        # filled_amount = self.total_donated_amount

        if filled_amount >= self.req_amount:
            proposer_proportion = 0
        else:
            proposer_proportion = Decimal((self.req_amount - filled_amount) / self.req_amount)
        if proposer_proportion > 0:
            reward_units = self.deck.epoch_quantity * (10 ** self.deck.number_of_decimals)
            self.proposer_reward = int(proposer_proportion * self.dist_factor * reward_units)
        else:
            self.proposer_reward = 0

    def validate_priority(self, tx_list, dist_round, debug=False):
        """Validates the priority of signalling and reserve transactions in round 2, 3, 5 and 6."""
        # New version with DonationStates, modified to validate a whole round list at once (more efficient).
        # Should be optimized in the beta/release version.
        # The type test seems ugly but is necessary unfortunately. All txes given to this method have to be of the same type.
        valid_txes = []

        # Slots are considered filled if 95% of the initial slot are locked or donated.
        # This prevents small rounding errors and P2TH/tx fees to make the slot invalid for the next rounds.
        # 95% allows a donation of 1 coin minus 0.04 fees, without having to add new outputs.
        fill_threshold = Decimal(0.95)

        if dist_round in (0, 3, 6, 7):
            return tx_list # rounds without priority check

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
            # print("VALID STATES", valid_dstates, "TYPE", type(tx_list[0]))
            if type(tx_list[0]) == LockingTransaction:
                try:
                    valid_rtx_txids = [dstate.locking_tx.txid for dstate in valid_dstates if dstate.locking_tx is not None]
                except AttributeError as e:
                    return []

        # Locking or DonationTransactions: we simply look for the DonationState including it
        # If it's not in any of the valid states, it can't be valid.

        # print("round here", dist_round)
        for tx in tx_list:
            if type(tx) in (LockingTransaction, DonationTransaction):
                try:
                    tx_dstate = valid_dstates[valid_rtx_txids.index(tx.txid)]
                except (IndexError, ValueError):
                    if debug: print("Transaction rejected by priority check:", tx.txid)
                    continue
            # In the case of signalling transactions, we must look for donation/locking TXes
            # using the spending address as donor address, because the used output can be another one.
            elif type(tx) == SignallingTransaction:
                for dstate in valid_dstates:
                    if dstate.donor_address in tx.input_addresses:
                        tx_dstate = dstate
                        break
                else:
                    if debug: print("Transaction rejected by priority check:", tx.txid)
                    continue

            try:
                if (dist_round < 4) and (tx_dstate.locking_tx.amount >= (Decimal(tx_dstate.slot) * fill_threshold)): # we could use the "complete" attribute? or only in the case of DonationTXes?
                    valid_txes.append(tx)
                elif (dist_round >= 4) and (tx_dstate.donation_tx.amount >= (Decimal(tx_dstate.slot) * fill_threshold)):
                    # TODO: should this not be the Locking Slot?
                    valid_txes.append(tx)

                else:
                    if debug: print("Reserve transaction rejected due to incomplete slot:", tx.txid, "\nSlot:", tx_dstate.slot, "Amount / Locked Amount:", tx_dstate.effective_slot, tx_dstate.effective_locking_slot)
                    continue
            except AttributeError:
                if debug: print("Required transaction (donation or locking) missing.")
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

class DonationState(object):
    # A DonationState contains Signalling, Locked and Donation transaction and the slot.
    # Must be created always with either SignallingTX or ReserveTX.

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

        if signalling_tx:
            self.donor_address = signalling_tx.address
            self.signalled_amount = signalling_tx.amount
            self.id = self.signalling_tx.txid
        elif reserve_tx:
            self.donor_address = reserve_tx.reserve_address
            self.reserved_amount = reserve_tx.reserved_amount
            self.id = self.reserve_tx.txid
        else:
            raise InvalidDonationStateError("A DonationState must be initialized with a signalling or reserve address.")

    def set_reward(self, proposal_state):
        if (self.effective_slot is not None) and (self.effective_slot > 0):
            slot_proportion = Decimal(self.effective_slot) / proposal_state.req_amount
            reward_units = proposal_state.deck.epoch_quantity * (10 ** proposal_state.deck.number_of_decimals)
            self.reward = int(slot_proportion * reward_units * proposal_state.dist_factor)

class InvalidDonationStateError(ValueError):
    # raised anytime when a DonationState is not following the intended format.
    pass

