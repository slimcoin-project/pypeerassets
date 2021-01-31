from pypeerassets.at.dt_slots import get_slot
from decimal import Decimal

class ProposalState(object):
   # A ProposalState unifies all functions from proposals which are mutable.
   # i.e. which can change after the first proposal transaction was sent.

    def __init__(self, valid_ptx, first_ptx, round_starts=[], round_halfway=[], signalling_txes=[], locking_txes=[], donation_txes=[], signalled_amounts=[], locked_amounts=[], donated_amounts=[], effective_slots=[], effective_locking_slots=[], donation_states=[], total_donated_amount=None, provider=None, current_blockheight=None, all_signalling_txes=[], all_donation_txes=[], all_locking_txes=[], dist_factor=None):

        self.valid_ptx = valid_ptx # the last proposal transaction which is valid.
        self.first_ptx = first_ptx # first ptx, in the case there was a Proposal Modification.
        # TODO: algorithm has to specify how the first ptx is selected.
        self.req_amount = valid_ptx.req_amount

        # The round length of the second phase (not the first one) can be changed in ProposalModifications. 
        # Thus all values based on round_length have 2 values, for the first and the second phase.
        self.round_lengths = [self.first_ptx.round_length, self.valid_ptx.round_length]
        self.security_periods = [max(l // 2, 2) for l in self.round_lengths]
        self.voting_periods = [l * 4 for l in self.round_lengths] # equal to a full slot distribution phase.
        self.release_period = self.voting_periods[1] # equal to the second phase voting period

        self.donation_address = self.first_ptx.donation_address
        self.deck = self.first_ptx.deck

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

        # The effective slot values are the sums of the effective slots in each round.
        self.effective_locking_slots = effective_locking_slots
        self.effective_slots = effective_slots

        # Factor to be multiplied with token amounts, between 0 and 1.
        # It depends on the Token Quantity per distribution period
        # and the number of coins required by the proposals in their ending period.
        # The higher the amount of proposals and their required amounts, the lower this factor is.
        self.dist_factor = dist_factor


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

            # print(self.round_starts)

    def set_donation_states(self, phase=0):
        # Version3. Uses the new DonationState class and the generate_donation_states method. 
        # Phase 0 means both phases are calculated.

        # If round starts are not set, or phase is 2 (re-defining of the second phase), then we set it.
        if len(self.round_starts) == 0 or (phase == 2):
            self.set_round_starts(phase)
            
        dstates = [{} for i in range(8)] # dstates is a list containing a dict with the txid of the signalling transaction as key
        rounds = (range(8), range(4), range(4,8))

        for rd in rounds[phase]:
            dstates[rd] = self._process_donation_states(rd)

        if phase in (0,1):
            self.donation_states = dstates
        elif phase == 2:
            self.donation_states[4:] = dstates[4:]

        self.total_donated_amount = sum(self.donated_amounts)


    def _process_donation_states(self, rd):
        # This function always must run chronologically, with previous rounds already completed.
        # It can, however, be run to redefine phase 2 (rd 4-7).
        # It sets also the attributes that are necessary for the next round and its slot calculation.

        # 1. determinate the valid signalling txes (include reserve/locking txes). 
        dstates = {}
        donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None

        all_stxes = [ stx for stx in self.all_signalling_txes if self.get_stx_dist_round == rd ]
        if rd in (0, 3, 6, 7):
             # first round, round 6 and first-come-first-serve rds: all signalling txes inside the blockheight limit.
             valid_stxes = all_stxes
             valid_rtxes = [] # No RTXes in these rounds.
        else:
             # TODO: Could be made more efficient, if necessary.
             if rd in (1, 2):
                 all_rtxes = [ltx for ltx in self.locking_txes[rd - 1] if ltx.reserved_amount > 0]
             elif rd == 4:
                 all_rtxes = [dtx for r in self.donation_txes[:4] for dtx in r if dtx.reserved_amount > 0]
             else:
                 all_rtxes = [dtx for dtx in self.donation_txes[rd - 1] if dtx.reserved_amount > 0]
             #stxes = [ stx for stx in all_stxes if self.validate_priority(stx, rd) == True ]          
             #rtxes = [ rtx for rtx in all_rtxes if self.validate_priority(rtx, rd) == True ]
             valid_stxes = self.validate_priority(all_stxes, rd)
             valid_rtxes = self.validate_priority(all_rtxes, rd)  

        # 2. Calculate total signalled amount and set other variables.

        self.signalling_txes[rd] = valid_stxes
        self.signalled_amounts[rd] = sum([tx.amount for tx in valid_stxes])
        self.reserve_txes[rd] = valid_rtxes
        self.reserved_amounts[rd] = sum([tx.reserved_amount for tx in valid_rtxes])
        # self.total_signalled_amount[rd] = self.signalled_amount + self.reserved_amount # Probably not needed.

        # 3. Generate DonationState and add locking/donation txes:
        # TODO: Do we need to validate the correct round of locking/donation, and even reserve txes?
        for tx in (valid_stxes + valid_rtxes):
            slot = get_slot(tx,
                            rd, 
                            signalling_txes=self.signalling_txes, 
                            locking_txes=self.locking_txes, 
                            donation_txes=self.donation_txes, 
                            signalled_amounts=self.signalled_amounts, 
                            reserved_amounts=self.reserved_amounts, 
                            locked_amounts=self.locked_amounts, 
                            donated_amounts=self.donated_amounts, 
                            first_req_amount=self.first_ptx.amount, 
                            final_req_amount=self.valid_ptx.amount,
                            effective_slots=self.effective_slots,
                            effective_locking_slots=self.effective_locking_slots)
            if rd < 4:
                locking_tx = tx.get_output_tx(self.all_locking_txes)
                # If the timelock is not correct, locking_tx is not added, and no donation tx is taken into account.
                # The DonationState will be incomplete in this case. Only the SignallingTx is being added.
                if self.validate_timelock(locking_tx):
                    self.locking_txes[rd].append(locking_tx)
                    self.locked_amounts[rd] + locking_tx.amount
                    effective_locking_slot = min(slot, locking_tx.amount)
                    donation_tx = locking_tx.get_output_tx(self.all_donation_txes)
            else:
                donation_tx = tx.get_output_tx(self.all_donation_txes)

            if donation_tx:
                effective_slot = min(slot, donation_tx.amount)
                self.donation_txes[rd].append(donation_tx)
                self.donated_amounts[rd] += donation_tx.amount

            # In round 1-4, the effectively locked slot amounts are the values which determinate the
            # slot rest for the next round. In round 5-8 it's the Donation effective slots.
            if effective_locking_slot:
                self.effective_locking_slots[rd] += effective_locking_slot
            if effective_slot:
                self.effective_slots[rd] += effective_slot
            
            dstate = DonationState(signalling_tx=tx, locking_tx=locking_tx, donation_tx=donation_tx, slot=slot, effective_slot=effective_slot, effective_locking_slot=effective_locking_slot, amount=donation_tx.amount, dist_round=rd)
    
            dstates.update({dstate.signalling_tx.txid, dstate})

        return dstates
               
    def get_stx_dist_round(self, stx):
        # This one only checks for the blockheight. Thus it can only be used for stxes.
       for rd in range(8):
           start = self.round_starts[rd]
           end = self.round_halfway[rd]

           if start <= stx.blockheight < end:
               return rd
           else:
               # raise InvalidTrackedTransactionError("Incorrect blockheight for a signalling transaction.")
               return None

    def set_dist_factor(self, ending_proposals):
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


    def validate_priority(self, tx_list, dist_round):
        """Validates the priority of signalling and reserve transactions in round 2, 3, 5 and 6."""
        # New version with DonationStates, modified to validate a whole round list at once (more efficient).
        # Should be optimized in the beta/release version.
        # The type test seems ugly but is necessary unfortunately. All txes given to this method have to be of the same type.
        valid_txes = []
        if dist_round in (0, 3, 6, 7):
            return tx_list # rounds without priority check

        elif dist_round == 4: # rd 5 is special because all donors of previous rounds are admitted.

            valid_dstates = [dstate for rd in (0, 1, 2, 3) for dstate in self.donation_states[rd]]
            if type(tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates]
        elif dist_round == 5:

            valid_dstates = [dstate for dstate in self.donation_states[4]]
            if type(tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates]        
        elif dist_round in (1, 2):
            valid_dstates = [dstate for dstate in self.donation_states[dist_round - 1]]
            if type(tx_list[0]) == LockingTransaction:
                valid_rtx_txids = [dstate.locking_tx.txid for dstate in valid_dstates]

        # Locking or DonationTransactions: we simply look for the DonationState including it
        # If it's not in any of the valid states, it can't be valid.
        for tx in tx_list:
            if type(tx) in (LockingTransaction, DonationTransaction):
                try:
                    tx_dstate = valid_dstates[valid_rtx_txids.index(tx.txid)]
                except IndexError:
                    continue
            # In the case of signalling transactions, we must look for donation/locking TXes
            # using the same spending address.
            elif type(tx) == SignallingTransaction:
                for dstate in valid_dstates:
                    if tx.address == dstate.donor_address:
                        tx_dstate = dstate
                        
            else:
                continue

            if (dist_round < 4) and (tx_dstate.locking_tx.amount >= tx_dstate.slot): # we could use the "complete" attribute? or only in the case of DonationTXes?
                valid_txes.append(tx)
            elif (dist_round >= 4) and (tx_dstate.donation_tx.amount >= tx_dstate.slot):
                valid_txes.append(tx)
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

    def __init__(self, signalling_tx=None, reserve_tx=None, locking_tx=None, donation_tx=None, slot=None, dist_round=None, effective_slot=None, effective_locking_slot=None):
        self.signalling_tx = signalling_tx
        self.reserve_tx = reserve_tx
        self.locking_tx = locking_tx
        self.donation_tx = donation_tx
        self.donated_amount = donation_tx.amount
        self.dist_round = dist_round
        self.slot = slot
        self.effective_slot = effective_slot
        self.effective_locking_slot = effective_locking_slot

        if signalling_tx:
            self.donor_address = signalling_tx.address
            self.signalled_amount = signalling_tx.amount
        elif reserve_tx:
            self.donor_address = reserve_tx.reserve_address
            self.reserved_amount = reserve_tx.reserved_amount
        else:
            raise InvalidDonationStateError("A DonationState must be initialized with a signalling or reserve address.")

class InvalidDonationStateError(ValueError):
    # raised anytime when a DonationState is not following the intended format.
    pass

