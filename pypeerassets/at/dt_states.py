from pypeerassets.at.dt_slots import get_raw_slot, get_first_serve_slot, get_priority_slot
from pypeerassets.at.dt_entities import TrackedTransaction, ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, InvalidTrackedTransactionError
from decimal import Decimal
from copy import deepcopy


class ProposalState(object):
    """A ProposalState contains all attributes from proposals which are mutable.
       i.e. which can change after the first proposal transaction was sent."""


    def __init__(self, valid_ptx: ProposalTransaction, first_ptx: ProposalTransaction, all_signalling_txes: int=None, all_locking_txes: int=None, all_donation_txes: int=None, all_voting_txes: int=None, **sub_state):

        self.first_ptx = first_ptx # First ProposalTransaction of the ProposalState..
        self.valid_ptx = valid_ptx # Last proposal transaction which is valid.

        self.req_amount = self.valid_ptx.req_amount # should work with ProposalModifications due to side effect
        self.id = self.first_ptx.txid # Identification. Does not change with Modifications.
        self.idstring = "[" + self.id[:16] + "] " + self.first_ptx.description # should be used to identify the Proposal in text and graphical interfaces, as descriptions are not unique (thus they're not called "names").

        self.donation_address = self.first_ptx.donation_address
        self.deck = self.first_ptx.deck

        # If there is a ProposalModification, set_rounds is called again (modify method).
        self.set_rounds()
        self.init_fresh_state()

        if sub_state:
            for key, value in sub_state.items():
                self.__setattr__(key, value)

    def init_fresh_state(self):

        self.donor_addresses = []
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
        # TODO: it seems as we now have total_reward, we don't really need dist_factor
        # as an attribute of proposal_state.
        # If eliminating it, take into account the variable is used once in pacli.
        self.dist_factor = None
        # Sum of all rewards corresponding to this proposal.
        self.total_reward = None

        # self.processed is a list of two values, one per phase.
        # It is set to True once the donation states of a phase are completely processed.
        self.processed = [False, False]  # MODIF: deleted third value, no longer needed!

        # If there are slots missing at the end, the proposer can claim the proportion.
        self.proposer_reward = None

    def set_rounds(self, modification: bool=False):
        # This method sets the start and end blocks of all rounds and periods.
        # When a proposal is recorded, both phases are calculated.
        # When a proposal has been modified, phase 2 is recalculated.

        # 1. Calculate round starts
        epoch_length = self.deck.epoch_length
        rd_unit = self.deck.standard_round_unit

        if not modification:

            self.rounds = [None] * 8
            self.security_periods = [None] * 2
            self.voting_periods = [None] * 2

        security_period_length = max(rd_unit, 2)  # minimum 2 blocks
        voting_period_length = release_period_length = rd_unit * 8
        preallocation_p1 = security_period_length + voting_period_length
        preallocation_p2 = preallocation_p1 + release_period_length

        # Phase 1 periods and rounds (processed only for proposal submissions,
        # as phase 1 rounds cannot be changed.)
        if not modification:

            # Proposal lifecycle begins in next epoch after the submission.
            self.start_epoch = self.first_ptx.epoch + 1
            self.dist_start = self.start_epoch * epoch_length

            # Required timelock consists in the original start of phase 2,
            # regardless of any proposal modifications.
            self.first_ptx.set_required_timelock(self.start_epoch)
            self.req_timelock = self.first_ptx.req_timelock
            self.security_periods[0] = [self.dist_start, self.dist_start + security_period_length - 1]
            voting_p1_start = self.security_periods[0][1] + 1
            self.voting_periods[0] = [voting_p1_start, voting_p1_start + voting_period_length - 1]
            dist_p1_start = self.dist_start + preallocation_p1

            # Slot distribution rounds
            for rd in range(4):
                 duration = rd_unit * 6 if rd == 0 else rd_unit * 2
                 start = dist_p1_start if rd == 0 else self.rounds[rd - 1][1][1] + 1
                 signalling_round = [start, start + (duration // 2) - 1]
                 locking_round = [start + (duration // 2), start + duration - 1]
                 self.rounds[rd] = [signalling_round, locking_round]

        # Phase 2 periods and rounds (processed for proposal submissals and modifications)
        self.end_epoch = self.start_epoch + self.valid_ptx.epoch_number + 1
        end_epoch_start = self.end_epoch * epoch_length
        dist_p2_start = self.end_epoch * epoch_length + preallocation_p2
        self.security_periods[1] = [end_epoch_start, end_epoch_start + security_period_length - 1]
        voting_p2_start = self.security_periods[1][1] + 1
        self.voting_periods[1] = [voting_p2_start, voting_p2_start + voting_period_length - 1]
        release_start = self.voting_periods[1][1] + 1
        self.release_period = [release_start, release_start + release_period_length - 1]

        for i in range(4):
            rd = i + 4
            duration = rd_unit * 2
            start = dist_p2_start + duration * i
            signalling_round = [start, start + (duration // 2) - 1]
            donation_round = [start + (duration // 2), start + duration - 1]
            self.rounds[rd] = [signalling_round, donation_round]

    def modify(self, debug=False):
        # This function bundles the steps needed when a valid Proposal Modification was recorded.
        # It doesn't need to reprocess set_donation_states, because this is only done
        # when a card is detected (after end_epoch) or when the parser loop ends.
        # Thus set_donation_states is never called before modify.

        # 1: Re-setting end epoch and rounds/periods for second phase.
        if self.first_ptx.epoch_number != self.valid_ptx.epoch_number:
            self.set_rounds(modification=True)
            self.end_epoch = self.start_epoch + self.valid_ptx.epoch_number

        # 2. Re-setting required coin amount and derivative attributes
        if self.first_ptx.req_amount != self.valid_ptx.req_amount:
            self.req_amount = self.valid_ptx.req_amount

        if debug:
            print("""PROPOSAL: Valid modification of proposal {} by transaction {}.
                     req_amount: {}, end_epoch: {}, rounds: {}""".format(self.first_ptx.txid,
                     self.valid_ptx.txid, self.req_amount, self.end_epoch, self.rounds))

    def set_donation_states(self, current_blockheight, debug=False):

        if len(self.rounds) == 0:
            if debug: print("PROPOSAL: Setting rounds for proposal:", self.id)
            self.set_rounds()

        # Incomplete donation states are marked as "abandoned" when the algorithm has processed
        # the end block of a round/period where a required transaction (locking or donation) was not found.
        # last_processed_round indicates the last round processed completely.

        last_processed_round = 7 # standard value: all rounds are processed.

        for rd_index, rd_blocks in enumerate(self.rounds):
            if current_blockheight <= rd_blocks[1][1]:
                last_processed_round = rd_index - 1  # if round 0 is not completely processed, result is -1.
                break

        self.available_slot_amount = [self.req_amount, None, None, None, None, None, None, None]

        # dstates is a list containing a dict with the txid of the signalling or reserve transaction as key
        self.donation_states = dstates = [{} for i in range(8)]

        # Once the proposal has ended and the number of proposals is known, the reward of each donor can be set
        # TODO: not strictly necessary, could be managed with an exception thrown if dist_factor is None
        set_reward = True if self.dist_factor is not None else False

        self.sorted_stxes, self.sorted_ltxes, self.sorted_dtxes = self._preprocess_tracked_txes()

        # Sets the direct successors, and additionally returns a list of all of them
        selected_successors = self.set_direct_successors()

        # all_tracked_txes = self.all_signalling_txes + self.all_locking_txes + self.all_donation_txes

        if debug:
            all_tracked_txes = self.sorted_stxes + self.sorted_ltxes + self.sorted_dtxes
            for tx in [tx for rd in all_tracked_txes for tx in rd]:
                if "direct_successor" in tx.__dict__:
                    print("DONATION: Direct successor for", tx.txid, type(tx), tx.direct_successor.txid, type(tx.direct_successor))
                if "reserve_successor" in tx.__dict__:
                    print("DONATION: Reserve successor for", tx.txid, type(tx), tx.reserve_successor.txid, type(tx.reserve_successor))

        if debug: print("All signalling txes:", self.all_signalling_txes)

        for rd in range(8):
            if rd == 4:
                self.available_slot_amount[rd] = self.req_amount - sum(self.effective_slots[:4])
            elif rd > 4:
                self.available_slot_amount[rd] = self.available_slot_amount[rd - 1] - self.effective_slots[rd - 1]
            elif rd > 0: # rounds 1, 2 and 3, 0 is already set
                self.available_slot_amount[rd] = self.available_slot_amount[rd - 1] - self.effective_locking_slots[rd - 1]

            dstates[rd] = self._process_donation_states(rd, selected_successors, debug=debug, set_reward=set_reward, last_processed_round=last_processed_round)
            if debug: print("Donation states of round", rd, ":", dstates[rd])

        self.donation_states = dstates
        self.processed[0] = True
        self.processed[1] = True

        self.total_donated_amount = sum(self.donated_amounts)
        if self.dist_factor is not None:
            self.set_proposer_reward()


    def _process_donation_states(self, rd, selected_successors, set_reward=False, last_processed_round=-1, debug=False):
        # This method always must run chronologically, with previous rounds already completed.
        # It sets also the attributes that are necessary for the next round and its slot calculation.

        # 1. determine the valid signalling txes (include reserve/locking txes).
        dstates = {}
        donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None
        round_stxes = self.sorted_stxes[rd]

        if debug: print("Checking signalling and reserve transactions of round", rd)
        if rd in (0, 3, 6, 7):

             valid_stxes = self._validate_basic(round_stxes, rd, selected_successors, reserve_mode=False, debug=debug)
             valid_rtxes = []  # No RTXes in these rounds.
             total_reserved_amount = 0
        else:
             # base_txes are all potential reserve transactions
             if rd in (1, 2):
                 base_txes = self.locking_txes[rd - 1]
             elif rd == 4:
                 base_txes = [t for rd in self.donation_txes[:4] for t in rd]
             else:
                 base_txes = self.donation_txes[rd - 1]

             raw_round_rtxes = sorted(base_txes, key = lambda x: (x.blockheight, x.blockseq))
             round_rtxes = self._validate_basic(raw_round_rtxes, rd, selected_successors, debug=debug, reserve_mode=True)

             if debug: print("DONATION: All possible reserve TXes in round:", rd, ":", [(t.txid, t.reserved_amount) for t in round_rtxes])

             # Reserve Transactions are validated first, as they have higher priority.
             valid_rtxes = self._validate_priority(round_rtxes, rd, selected_successors, reserve_mode=True, debug=debug) if len(round_rtxes) > 0 else []
             total_reserved_amount = sum([tx.reserved_amount for tx in valid_rtxes])
             if debug: print("DONATION: Total reserved in round {}: {} - Available slot amount: {}".format(rd, total_reserved_amount, self.available_slot_amount[rd]))

             # If the amount signalled in reserve transactions exceeds the total available slots,
             # do not process signalling transactions, as they would lead to slots with 0 due to their lower priority.
             if total_reserved_amount > self.available_slot_amount[rd]:
                 # Successors of invalid signalling transactions are deleted from successor list
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

        # 3. Generate DonationState, select definitive successors, and add locking/donation txes:

        # sort origin transactions, as they're here not in chronologic order as they are of 2 distinct types.
        # MODIF: rtxes are earlier in the chain (in the round before), sorting is probably not needed.
        all_origin_txes = sorted(valid_rtxes + valid_stxes, key = lambda x: (x.blockheight, x.blockseq))

        for tx in all_origin_txes:

            donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None

            # Initial slot: based on signalled amount.
            slot = self.get_slot(tx, rd, debug=debug)
            if debug: print("SLOT: Slot for tx", tx.txid, ":", slot)

            if slot == 0:
                if debug: print("SLOT: Donation state with slot zero not created.")
                try:
                   if tx.direct_successor.txid in selected_successors:
                       # NOTE: we don't have to delete the donor address of a DonationTX here, because the tx will be ignored anyway.
                       self._delete_invalid_successor(tx.direct_successor, selected_successors)
                except AttributeError:
                   pass
                continue

            if rd < 4:
                locking_tx = self._get_ttx_successor(rd, tx, self.sorted_ltxes[rd], selected_successors, debug=debug, mode="origin")

                # If the timelock is not correct, the LockingTransaction is not added, and no DonationTransaction is taken into account.
                # The DonationState will be incomplete/abandoned in this case. Only the SignallingTx is being added.
                if (locking_tx is not None) and locking_tx.timelock >= self.req_timelock:


                    # TODO is this really the most efficient way?
                    ltxes = deepcopy(self.locking_txes)
                    ltxes[rd].append(locking_tx)
                    self.locking_txes = ltxes

                    self.locked_amounts[rd] += locking_tx.amount
                    effective_locking_slot = min(slot, locking_tx.amount)

                    if debug: print("DONATION: Lookup Successor for locking tx:", locking_tx.txid)

                    # special case: all potential successors of donation transactions in rounds 0-3 are in round 0 (see above).
                    donation_tx = self._get_ttx_successor(rd, locking_tx, self.sorted_dtxes[0], selected_successors, debug=debug)
                    if debug and donation_tx: print("DONATION: Donation tx added in locking mode", donation_tx.txid, rd)

            else:
                if debug: print("DONATION: Lookup Successor for reserve/signalling tx:", tx.txid)
                donation_tx = self._get_ttx_successor(rd, tx, self.sorted_dtxes[rd], selected_successors, debug=debug, mode="origin")
                if debug and donation_tx: print("DONATION: Donation tx added in donation mode", donation_tx.txid, rd)

            if donation_tx:
                self.donation_txes[rd].append(donation_tx)
                self.donated_amounts[rd] += donation_tx.amount

            dstate = DonationState(proposal_id=self.id, origin_tx=tx, locking_tx=locking_tx, donation_tx=donation_tx, slot=slot, effective_slot=effective_slot, effective_locking_slot=effective_locking_slot, dist_round=rd)

            dstate.set_effective_slot(last_processed_round)

            # In round 1-4, the effectively locked slot amounts are the values which determinate the
            # slot rest for the next round. In round 5-8 it's the Donation effective slots.
            if dstate.effective_locking_slot and (rd < 4):
                self.effective_locking_slots[rd] += dstate.effective_locking_slot
            if dstate.effective_slot:
                self.effective_slots[rd] += dstate.effective_slot

            if set_reward:
                dstate.set_reward(self)

            dstates.update({dstate.id : dstate})

        return dstates

    def _delete_invalid_successor(self, successor_tx, selected_successors):
        if successor_tx is None:
            return
        txid = successor_tx.txid

        if txid in selected_successors:
            txid_index = selected_successors.index(txid)

            # second level: if locking tx is deleted, donation tx must also be deleted.
            if type(successor_tx) == LockingTransaction:
                for successor_attr in ("direct_successor", "reserve_successor"):
                    try:
                        l2_successor = successor_tx.__dict__[successor_attr]
                    except KeyError:
                        continue

                    if l2_successor.txid in selected_successors:
                        l2_txid_index = selected_successors.index(l2_successor.txid)
                        del selected_successors[l2_txid_index]

            del selected_successors[txid_index]

    def _validate_basic(self, origin_tx_list, rd, selected_successors, reserve_mode=False, debug=False, add_address=True):
        # basic validation steps previous to the creation of a new Donation State:
        # donor address duplication, reserve address existence, proposer identity.
        result = []

        # Origin transactions (signalling / reserve) are checked and get successors
        for tx in origin_tx_list:
            if reserve_mode:
                successor_tx = tx.reserve_successor if "reserve_successor" in tx.__dict__ else None
                donor_address = tx.reserve_address
                if not tx.reserved_amount:
                    if debug: print("DONATION: Potential reserve transaction", tx.txid, "rejected, no reserved amount.")
                    continue
            else:
                successor_tx = tx.direct_successor if "direct_successor" in tx.__dict__ else None
                donor_address = tx.donor_address

            # Proposers cannot be donors
            if donor_address == self.donation_address:
                if debug: print("DONATION: Proposer {} trying to donate, this is invalid. No donation state created.".format(address))
                if successor_tx is not None:
                    self._delete_invalid_successor(successor_tx, selected_successors)
                continue

            if self.check_donor_address(tx, rd, donor_address, add_address=add_address, reserve=reserve_mode, debug=debug):
                result.append(tx)

            elif successor_tx is not None:
                self._delete_invalid_successor(successor_tx, selected_successors)

        return result

    def _get_ttx_successor(self, rd: int, tx: TrackedTransaction, potential_successors: list, selected_successors: list, mode: str=None, debug: bool=False) -> TrackedTransaction:
        """This method definitively selects the successor of a SignallingTransaction or LockingTransaction."""

        try:
            # origin mode: when Locking/Donation transactions are checked as origin transactions,
            # we select the reserve successor
            if mode == "origin" and type(tx) != SignallingTransaction:
                reserve_mode = True
                selected_tx = tx.reserve_successor
            else:
                reserve_mode = False
                selected_tx = tx.direct_successor

            if type(selected_tx) == DonationTransaction:
                selected_tx.set_donor_address(direct_predecessor=tx)

        except AttributeError: # successor still not existing

            indirect_successors = tx.get_indirect_successors(potential_successors, reserve_mode=reserve_mode)
            if debug: print("DONATION: Indirect Successors of tx", tx.txid, ":" ,[t.txid for t in indirect_successors])

            for suc_tx in indirect_successors:

                # MODIF: round checks not necessary, as the txes are already restricted for a round.
                if (suc_tx.txid not in selected_successors): # and (self.check_round(suc_tx, rd)):
                    selected_tx = suc_tx
                    selected_successors.append(selected_tx.txid)

                    if type(selected_tx) == DonationTransaction:
                        selected_tx.set_donor_address(direct_predecessor=tx)
                    break
                elif debug:
                    if suc_tx.txid in selected_successors:
                        print("DONATION: Successor", suc_tx.txid, "rejected: is already a successor of a valid earlier transaction.")
                    #if not self.check_round(suc_tx, rd): ### MODIF: validate -> check
                    #    print("DONATION: Successor", suc_tx.txid, "rejected: blockheight out of round", rd)
            else:
                selected_tx = None


        return selected_tx

    def check_donor_address(self, tx, rd, addr, reserve=False, add_address=False, debug=False):
        # Checks if a donor address of a transaction was already used in the same phase for the same tx type.
        # add_address is needed because there are cases where the addition occurs later.
        # TODO: Due to the "child states" introduced recently, there is no need anymore to allow
        # duplicate donor addresses for phase 1 and 2. This could be an important simplification.
        phase = rd // 4
        if debug: print("DONATION: Checking tx", tx.txid, "with address", tx.donor_address)

        # Reserve transactions count as signalling transactions for this list,
        # otherwise a duplicate starting with signalling/reserve tx would be permitted.
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

    def _preprocess_tracked_txes(self):
        # MODIF: It is better we sort and segregate already at the start of the processing,
        # even if there are more txes to sort/segregate, the efficiency gains are very high.
        result = []
        for group_index, tx_group in enumerate((self.all_signalling_txes, self.all_locking_txes, self.all_donation_txes)):
            sorted_tx_group = []
            rng = (8, 4, 8) # locking txes list is only 4 rounds long
            tx_group.sort(key = lambda x: (x.blockheight, x.blockseq))

            for rd in range(rng[group_index]):
                rd_txes = []
                for tx in tx_group:
                    if self.check_round(tx, rd):
                        # Special case: we can't set the DonationTxes' dist round in rd 0-3,
                        # as they're all present in the same release period.
                        # They are however added to dist_round 0.
                        if (type(tx) != DonationTransaction) or (rd >= 4):
                            tx.set_dist_round(rd)
                        rd_txes.append(tx)

                sorted_tx_group.append(rd_txes)

            result.append(sorted_tx_group)

        return result

    def set_direct_successors(self):
        selected_successors = []
        for rd in range(8):
            for stx in self.sorted_stxes[rd]:
                if rd < 4:
                    if stx.set_direct_successor(self.sorted_ltxes[rd]):
                        selected_successors.append(stx.direct_successor)
                else:
                    if stx.set_direct_successor(self.sorted_dtxes[rd]):
                        selected_successors.append(stx.direct_successor)
            if rd < 4:
                for ltx in self.sorted_ltxes[rd]:
                    if rd < 3:
                        if ltx.set_direct_successor(self.sorted_ltxes[rd + 1], reserve_mode=True):
                            selected_successors.append(ltx.reserve_successor)
                    # Donation transactions of the first 4 rounds are in group 0
                    if ltx.set_direct_successor(self.sorted_dtxes[0]):
                        selected_successors.append(ltx.direct_successor)

            if rd < 7:
                for dtx in self.sorted_dtxes[rd]:
                    if dtx.set_direct_successor(self.sorted_dtxes[rd + 1], reserve_mode=True):
                        selected_successors.append(dtx.reserve_successor)

        return selected_successors


    def set_dist_factor(self, ending_proposals):
        # Proposal factor: if there is more than one proposal ending in the same epoch,
        # the resulting slot is divided by the req_amounts of them.
        # NOTE: total_reward added, it simplifies the reward calculation.

        if len(ending_proposals) > 1:
            total_req_amount = sum([p.req_amount for p in ending_proposals])
            self.dist_factor = Decimal(self.req_amount) / total_req_amount
        else:
            self.dist_factor = Decimal(1)

        self.total_reward = self.deck.epoch_reward * (10 ** self.deck.number_of_decimals) * self.dist_factor

    def set_proposer_reward(self):
        filled_amount = sum(self.effective_slots)

        if filled_amount >= self.req_amount:
            proposer_proportion = 0
        else:
            proposer_proportion = Decimal((self.req_amount - filled_amount) / self.req_amount)

        if proposer_proportion > 0:
            self.proposer_reward = int(proposer_proportion * self.total_reward)
        else:
            self.proposer_reward = 0

    def _validate_priority(self, origin_tx_list: list, dist_round: int, selected_successors: list, reserve_mode: bool=False, debug: bool=False):
        """Validates the priority of signalling and reserve transactions in round 2, 3, 5 and 6."""
        # New version with DonationStates, modified to validate a whole round list at once (more efficient).
        # Should be optimized in the beta/release version.
        # The type test seems ugly but is necessary unfortunately. All txes given to this method have to be of the same type.
        # Method is called only in the rounds with priority mechanism (1, 2, 4, 5), thus dist_round doesn't check for other values.
        valid_txes = []

        # Slots are considered filled if 95% of the initial slot are locked or donated.
        # This prevents small rounding errors and P2TH/tx fees to make the slot invalid for the next rounds.
        # 95% allows a donation of 1 coin minus 0.04 fees, without having to add new UTXOs.
        fill_threshold = Decimal(0.95)

        if dist_round == 4: # rd 5 is special because all donors of previous rounds are admitted.

            valid_dstates = [dstate for rd in (0, 1, 2, 3) for dstate in self.donation_states[rd].values()]

            if type(origin_tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates if dstate.donation_tx is not None]

        elif dist_round == 5:

            valid_dstates = [dstate for dstate in self.donation_states[4].values()]

            if type(origin_tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates if dstate.donation_tx is not None]

        elif dist_round in (1, 2):

            valid_dstates = [dstate for dstate in self.donation_states[dist_round - 1].values()]
            if type(origin_tx_list[0]) == LockingTransaction:
                try:
                    valid_rtx_txids = [dstate.locking_tx.txid for dstate in valid_dstates if dstate.locking_tx is not None]
                except AttributeError as e:
                    return []

        # Locking or DonationTransactions: we simply look for the DonationState including it
        # If it's not in any of the valid states, it can't be valid.

        for tx in origin_tx_list:

            # Assign successor first
            try:
                if reserve_mode:
                    successor_tx = tx.reserve_successor
                else:
                    successor_tx = tx.direct_successor
            except AttributeError:
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
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue
                parent_dstate = dstate

            # In the case of signalling transactions, we must look for donation/locking TXes
            # using the spending address as donor address, because the used output can be another one.
            elif type(tx) == SignallingTransaction:

                # Donor address check is done first, but without adding addresses; we do this at the end of validation.
                # We don't check donor addresses for Locking/Donation txes, they are checked earlier.
                if not self.check_donor_address(tx, dist_round, tx.donor_address, add_address=False, debug=debug):
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue

                for dstate in valid_dstates:
                    #if debug: print("Donation state checked:", dstate.id, "for tx", tx.txid, "with input addresses", tx.input_addresses)
                    if dstate.donor_address in tx.input_addresses:

                        parent_dstate = dstate
                        self.add_donor_address(tx.donor_address, tx.ttx_type, (dist_round // 4))
                        break
                else:
                    if debug: print("Transaction rejected by priority check:", tx.txid)
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue

            try:

                if (dist_round < 4) and (parent_dstate.locking_tx.amount >= (Decimal(parent_dstate.slot) * fill_threshold)): # we could use the "complete" attribute? or only in the case of DonationTXes?
                    valid_txes.append(tx)
                    parent_dstate.child_state_ids.append(tx.txid)
                elif (dist_round >= 4) and (parent_dstate.donation_tx.amount >= (Decimal(parent_dstate.slot) * fill_threshold)):
                    valid_txes.append(tx)
                    parent_dstate.child_state_ids.append(tx.txid)
                else:
                    if debug: print("Reserve transaction rejected due to incomplete slot of parent donation state:", tx.txid, "\nSlot:", parent_dstate.slot, "Effective Slot (donated amount): {} Locking Slot: {}".format(parent_dstate.effective_slot, parent_dstate.effective_locking_slot))
                    self._delete_invalid_successor(successor_tx, selected_successors)
                    continue
            except AttributeError as e:
                if debug: print("Required transaction (donation or locking) of parent donation state missing:", tx.txid)
                if debug: print(e)
                continue

        return valid_txes

    def check_round(self, tx: TrackedTransaction, dist_round: int) -> bool:
        """Checks in which round a transaction was sent."""

        if type(tx) == DonationTransaction and dist_round < 4:
            startblock = self.release_period[0]
            endblock = self.release_period[1]
        elif type(tx) == SignallingTransaction: # MODIF: added, to get rid of the signalling_tx round function.
            startblock = self.rounds[dist_round][0][0]
            endblock = self.rounds[dist_round][0][1]
        else:
            startblock = self.rounds[dist_round][1][0]
            endblock = self.rounds[dist_round][1][1] # last valid block

        if (startblock <= tx.blockheight <= endblock):
            return True
        else:
            return False

    def get_slot(self, tx: TrackedTransaction, dist_round: int, debug: bool=False) -> int:
        """Assigns a slot to a Signalling/Reserve transaction."""

        # Check transaction type (signalling or donation/locking):
        # This works because SignallingTransactions have no attribute .reserved_amount and thus throw AttributeError.
        try:
            tx_amount = tx.reserved_amount
            if dist_round in (0, 3, 6, 7): # Reserve transactions are not valid in these rounds.
                raise ValueError("No reserve transactions in this round.")
        except AttributeError:
            tx_amount = tx.amount

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

    def process_votes(self, enabled_voters: dict, phase: int, formatted_result: bool=False, debug: bool=True):
        # stores a dictionary in initial/final votes with two keys: "positive" and "negative",
        # weighted by the amounts of the tokens belonging to the voters of a proposal.
        # NOTE: The balances are valid for the epoch of the ParserState. So this cannot be called
        #       for votes in other epochs.
        # NOTE 2: In this protocol the last vote counts (this is why the vtxs list is reversed).
        #       You can always change you vote.
        # Formatted_result returns the "decimal" value of the votes, i.e. the number of "tokens"
        # which voted for the proposal, which depends on the "number_of_decimals" value.
        # NOTE 3: This method is now called by phase, it is more transparent and efficient.

        votes = { "negative" : 0, "positive" : 0 }
        voters = [] # to filter out duplicates.

        if phase == 0:
            self.initial_votes = votes
        elif phase == 1:
            self.final_votes = votes

        if debug: print("VOTING: Enabled Voters:", enabled_voters)

        if len(self.all_voting_txes) == 0:
            return

        voting_epoch = self.start_epoch if phase == 0 else self.end_epoch
        phase_vtxes = [v for v in self.all_voting_txes if v.epoch == voting_epoch]
        sorted_vtxes = sorted(phase_vtxes, key=lambda tx: (tx.blockheight, tx.blockseq), reverse=True)

        for v in sorted_vtxes: # reversed for the "last vote counts" rule.
            if debug: print("VOTING: Vote: Epoch", v.epoch, "txid:", v.txid, "sender:", v.sender, "outcome:", v.vote, "height", v.blockheight)
            if v.sender not in voters:
                try:
                    if debug: print("VOTING: Vote is valid.")
                    voter_balance = enabled_voters[v.sender] # voting token balance at start of epoch
                    if debug: print("VOTING: Voter balance", voter_balance)
                    vote_outcome = "positive" if v.vote else "negative"
                    votes[vote_outcome] += voter_balance
                    if debug: print("VOTING: Balance of outcome", vote_outcome, "increased by", voter_balance)
                    voters.append(v.sender)

                    # set the weight in the transaction (vote_weight attribute)
                    v.set_weight(voter_balance)

                    # Valid voting txes are appended to ProposalStates.voting_txes by round and outcome
                    self.voting_txes[phase].append(v)

                except KeyError: # will always be thrown if a voter is not enabled in the "current" epoch.
                    if debug: print("VOTING: Voter has no balance in the current epoch.")
                    continue

        if formatted_result:
            for outcome in ("positive", "negative"):
                balance = Decimal(votes[outcome]) / 10 ** self.deck.number_of_decimals
                votes.update({outcome : balance})


class DonationState(object):
    # A DonationState contains Signalling, Locking and Donation transaction and the slot.
    # Must be created always with either SignallingTX or ReserveTX.
    # Child_state_id allows more control over inheriting.
    # The "claimed" state is assigned in the ParserState loop.

    def __init__(self, proposal_id=None, origin_tx=None, locking_tx=None, donation_tx=None, slot=None, dist_round=None, effective_slot=None, effective_locking_slot=None, reward=None, state="incomplete"):

        self.proposal_id = proposal_id
        self.origin_tx = origin_tx
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

        if type(origin_tx) == SignallingTransaction:
            self.signalling_tx = origin_tx
            self.reserve_tx = None
        elif type(origin_tx) in (LockingTransaction, DonationTransaction):
            self.reserve_tx = origin_tx
            self.signalling_tx = None

        if self.signalling_tx is not None:
            self.donor_address = self.origin_tx.donor_address
            self.signalled_amount = self.origin_tx.amount
        elif self.reserve_tx is not None:
            self.donor_address = self.origin_tx.reserve_address
            self.signalled_amount = self.origin_tx.reserved_amount
        else:
            raise InvalidDonationStateError("A DonationState must be initialized with a signalling or reserve address.")

        self.id = self.origin_tx.txid


    def set_reward(self, proposal_state):

        if (self.effective_slot is not None) and (self.effective_slot > 0):
            slot_proportion = Decimal(self.effective_slot) / proposal_state.req_amount
            self.reward = int(slot_proportion * proposal_state.total_reward)

    def set_effective_slot(self, last_processed_round):

        if self.donation_tx:
            if self.dist_round < 4:
                self.effective_slot = min(self.effective_locking_slot, self.donation_tx.amount)

            else:
                self.effective_slot = min(self.slot, self.donation_tx.amount)

            self.state = "complete" if (self.effective_slot > 0) else "abandoned"

        elif last_processed_round >= self.dist_round:

            if self.dist_round < 4:
                # if we're in the first 4 rounds, then states with missing donation tx continue to be
                # incomplete as long as they cointain a locking tx.
                # if round 4 was processed, then these states are abandoned as we're post release phase
                if (self.locking_tx is None) or ((self.donation_tx is None) and (last_processed_round >= 4)):
                    self.state = "abandoned"
            else:
               self.state = "abandoned"


class InvalidDonationStateError(ValueError):
    # raised anytime when a DonationState is not following the intended format.
    pass

