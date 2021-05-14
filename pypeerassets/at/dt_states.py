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

class ProposalState(object):
   # A ProposalState unifies all functions from proposals which are mutable.
   # i.e. which can change after the first proposal transaction was sent.

    def __init__(self, valid_ptx, first_ptx, round_starts=[], round_halfway=[], signalling_txes=linit(), locking_txes=linit(), donation_txes=linit(), signalled_amounts=linitz(), locked_amounts=linitz(), donated_amounts=linitz(), reserve_txes=linit(), reserved_amounts=linitz(), effective_slots=linitz(), effective_locking_slots=linitz(), donation_states=[], total_donated_amount=None, provider=None, current_blockheight=None, all_signalling_txes=[], all_donation_txes=[], all_locking_txes=[], donor_addresses=[], initial_votes=None, final_votes=None, dist_factor=None, processed=None, proposer_reward=None):

        self.valid_ptx = valid_ptx # the last proposal transaction which is valid.
        self.first_ptx = first_ptx # first ptx, in the case there was a Proposal Modification.
        # TODO: algorithm has to specify how the first ptx is selected.
        self.req_amount = valid_ptx.req_amount
        self.id = self.first_ptx.txid # Identification. Does not change with Modifications.

        # The round length of the second phase (not the first one) can be changed in ProposalModifications. 
        # Thus all values based on round_length have 2 values, for the first and the second phase.
        self.round_lengths = [self.first_ptx.round_length, self.valid_ptx.round_length]
        self.security_periods = [max(l // 2, 2) for l in self.round_lengths]
        self.voting_periods = [l * 4 for l in self.round_lengths] # equal to a full slot distribution phase.
        self.release_period = self.voting_periods[1] # equal to the second phase voting period

        self.donation_address = self.first_ptx.donation_address
        self.deck = self.first_ptx.deck
        self.donor_addresses = donor_addresses

        # Slot Allocation Round Attributes are lists with values for each of the 8 distribution rounds
        # Phase 2 can vary if there is a ProposalModification, so this can be set various times.
        if not round_starts:
            self.set_round_starts(phase=0)
        else:
            self.round_starts = round_starts
            self.round_halfway = round_halfway
            self.dist_start = dist_start # start block of first voting/distribution round.

        deck = self.first_ptx.deck

        if not current_blockheight and (not signalling_txes or not donation_txes):
            current_blockheight = provider.getblockcount()

        # New: Attributes for all TrackedTransactions without checking them (with the exception of VotingTransactions)
        self.all_signalling_txes = all_signalling_txes
        self.all_locking_txes = all_locking_txes
        self.all_donation_txes = all_donation_txes

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
        self.initial_votes = initial_votes
        self.final_votes = final_votes

        # The effective slot values are the sums of the effective slots in each round.
        self.effective_locking_slots = effective_locking_slots
        self.effective_slots = effective_slots

        # State: The general state of the proposal. At the start until the first voting round it is set to active.
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
            self.processed = [False, False, False]
        else:
            self.processed = processed

        # If there are slots missing at the end, the proposer can claim the proportion.
        self.proposer_reward = proposer_reward


    def set_round_starts(self, phase=0):
        # all rounds of first or second phase
        # It should be ensured that this method is only called once per phase, or when a proposal has been modified.

        epoch_length = self.valid_ptx.deck.epoch_length

        self.round_starts = [None] * 9
        self.round_halfway = [None] * 9

        halfway = self.first_ptx.round_length // 2
        pre_allocation_period_phase1 = self.security_periods[0] + self.voting_periods[0]
        pre_allocation_period_phase2 = self.security_periods[1] + self.voting_periods[1] + self.release_period
        # phase 0 means: both phases are calculated.

        if phase in (0, 1):
            distribution_length = pre_allocation_period_phase1 + (self.round_lengths[0] * 4)
            # blocks in epoch: blocks which have passed since last epoch start.
            # blocks_in_epoch = self.first_ptx.blockheight - (self.start_epoch * epoch_length) # MODIFIED, TODO: Re-check!
            blocks_in_epoch = self.first_ptx.blockheight % epoch_length # modified to modulo.
            blocks_remaining = epoch_length - blocks_in_epoch
            # print("dl", distribution_length, "bie", blocks_in_epoch, "el", epoch_length)
            

            # if proposal can still be voted and slots distributed, then do it in the current epoch.
            if blocks_remaining > distribution_length:

                # MODIFIED. Introduced dist_start to avoid confusion regarding the voting period.
                # MODIFIED 2. Start epoch is now the start of the DISTRIBUTION epoch.
                self.start_epoch = self.first_ptx.epoch
                self.dist_start = self.first_ptx.blockheight
            else:
                self.start_epoch = self.first_ptx.epoch + 1
                self.dist_start = self.start_epoch * epoch_length # MODIFIED.

            # MODIFIED: end epoch is 1 after last working epoch.
            self.end_epoch = self.start_epoch + self.valid_ptx.epoch_number + 1 

            phase_start = self.dist_start + pre_allocation_period_phase1

            for i in range(4): # first phase has 4 rounds
                self.round_starts[i] = phase_start + self.round_lengths[0] * i
                self.round_halfway[i] = self.round_starts[i] + halfway

        if phase in (0, 2):

            epoch = self.end_epoch # final vote/distribution should always begin at the start of the end epoch.
            phase_start = self.end_epoch * epoch_length + pre_allocation_period_phase2

            for i in range(5): # second phase has 5 rounds, the last one being the Proposer round.
                # we use valid_ptx here, this gives the option to change the round length of 2nd round.
                # TODO: should we really make this value changeable? This prevents us to set an unitary round_length value.
                self.round_starts[i + 4] = phase_start + self.round_lengths[1] * i
                self.round_halfway[i + 4] = self.round_starts[i + 4] + halfway

        self.set_rounds(phase)

    def set_rounds(self, phase=0):
        rounds = []
        # complements round_starts, should replace them in many functions. Above all useful because of round 4.
        # first element is the signalling period, second one the locking/donation period.
        # TODO: shouldn't this be extended to all phases of the proposal lifecycle?
        # TODO: there is ambiguity in round 4 (first second-round round). It should be in theory
        # possible to donate based on reserve txes from round 0-3 there, which would mean to have
        # a special donation period AFTER the donation release phase. Currently the signalling
        # period is rd 0-3 and the donation release phase the donation phase, which seems wrong.
        if phase == 2:
            round_length = self.round_lengths[1] # if phase 2 reorganisation, we take valid_ptx, otherwise first_ptx.
        else:
            round_length = self.round_lengths[0]

        for rd in range(8):
            rds = [None,None]
            rds[0] = [self.round_starts[rd], self.round_halfway[rd] - 1]
            rds[1] = [self.round_halfway[rd], self.round_starts[rd] + round_length - 1]
            rounds.append(rds)
        self.rounds = rounds        


    def set_donation_states(self, phase=0, current_blockheight=None, debug=False):
        # Version3. Uses the new DonationState class and the generate_donation_states method. 
        # Phase 0 means both phases are calculated.
        # debug = True ## TEST
        #if debug: print("DONATION STATES: Setting for PROPOSAL:", self.id)
        # If round starts are not set, or phase is 2 (re-defining of the second phase), then we set it.
        # for May tests:
        # debug = True if self.id == "41e38b09b07147a794d79916c8128612378bfaece0231ad5efa13a08a2fb588f" else False
        if len(self.round_starts) == 0 or (phase == 2):
            if debug: print("Setting round starts for PROPOSAL:", self.id)
            self.set_round_starts(phase)

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

        # If the first phase is re-processed or if there was a incomplete processing the donor address list is reset
        if phase in (0, 1) or self.processed[2] == False:
            self.donor_addresses = []

        self.donation_states = dstates = [{} for i in range(8)] # dstates is a list containing a dict with the txid of the signalling or reserve transaction as key
        rounds = (range(8), range(4), range(4,8))

        # Once the proposal has ended and the number of proposals is known, the reward of each donor can be set
        set_reward = True if self.dist_factor is not None else False

        #if debug: print("All signalling txes:", self.all_signalling_txes)
        for rd in rounds[phase]:
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
        self.locked_amounts[rd] = 0
        self.effective_locking_slots[rd] = 0
        self.effective_slots[rd] = 0
        self.donated_amounts[rd] = 0
        # self.total_signalled_amount[rd] = self.signalled_amount + self.reserved_amount # Probably not needed.

        # 3. Generate DonationState and add locking/donation txes:
        # TODO: Do we need to validate the correct round of locking/donation, and even reserve txes?
        for tx in (valid_stxes + valid_rtxes):
            donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None
            state = "incomplete"
            # Initial slot: based on signalled amount.
            slot = get_slot(tx,
                            rd, 
                            signalling_txes=self.signalling_txes, 
                            locking_txes=self.locking_txes,
                            donation_txes=self.donation_txes,
                            signalled_amounts=self.signalled_amounts, 
                            reserved_amounts=self.reserved_amounts, 
                            locked_amounts=self.locked_amounts, 
                            donated_amounts=self.donated_amounts, 
                            first_req_amount=self.first_ptx.req_amount, 
                            final_req_amount=self.valid_ptx.req_amount,
                            effective_slots=self.effective_slots,
                            effective_locking_slots=self.effective_locking_slots)
            if debug: print("Slot for tx", tx.txid, ":", slot)
            if rd < 4:
                locking_tx = tx.get_output_tx(self.all_locking_txes, self, rd, self.rounds)
                # If the timelock is not correct, locking_tx is not added, and no donation tx is taken into account.
                # The DonationState will be incomplete in this case. Only the SignallingTx is being added.
                if (locking_tx is not None) and self.validate_timelock(locking_tx):
                    #print("locking txes before", [t.txid for rd in self.locking_txes for t in rd])
                    ltxes = deepcopy(self.locking_txes)
                    ltxes[rd].append(locking_tx)
                    self.locking_txes = ltxes
                    # print("adding locking tx", locking_tx.txid, "in round", rd)
                    #print("locking_txes after", [t.txid for rd in self.locking_txes for t in rd])
                    # TODO: There are amounts at round 4 which should not be there.
                    self.locked_amounts[rd] += locking_tx.amount
                    effective_locking_slot = min(slot, locking_tx.amount)
                    # print("EFFECTIVE LOCKING SLOT RD", rd, effective_locking_slot, slot, locking_tx.amount, locking_tx.txid, self.locked_amounts)
                    # print("Searching child txes of locking tx", locking_tx.txid)
                    donation_tx = locking_tx.get_output_tx(self.all_donation_txes, self, rd, self.rounds, mode="locking")
                    if debug and donation_tx: print("Donation tx added in locking mode", donation_tx.txid, rd)
                    # if donation_tx: print("Donation tx added in locking mode", donation_tx.txid, rd)
                    
            else:
                # print("Searching child txes of tx", tx.txid, "of type", type(tx))
                donation_tx = tx.get_output_tx(self.all_donation_txes, self, rd, self.rounds)
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
            if effective_locking_slot:
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
           start = self.round_starts[rd]
           end = self.round_halfway[rd] - 1

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

