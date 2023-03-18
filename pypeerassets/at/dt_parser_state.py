""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch, instead by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, VotingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.transaction_formats import *
from pypeerassets.at.dt_parser_utils import *
# from pypeerassets.__main__ import find_deck # circular import, TODO refactor.
import pypeerassets.at.constants as c
import pypeerassets as pa
from copy import deepcopy

class ParserState(object):
    """A ParserState contains the current state of all important variables for a single deck,
       while the card parser is running.
       A sub_state is a dict to allow to create a ParserState in a pre-processed state.
       Currently not used but maybe useful."""

    def __init__(self, deck: object, initial_cards: list, provider: object, epoch: int=None, start_epoch: int=None, end_epoch: int=None,  current_blockheight: int=None, debug: bool=False, debug_voting: bool=False, debug_donations: bool=False, epochs_with_completed_proposals: int=0, **sub_state):

        self.deck = deck
        self.initial_cards = initial_cards
        self.provider = provider

        # new debugging system: divided into donations processing and voting
        # self.debug stays for general messages
        if debug:
            self.debug_voting = True
            self.debug_donations = True
        else:
            self.debug_voting = debug_voting
            self.debug_donations = debug_donations

        if self.debug_voting or self.debug_donations:
            self.debug = True
        else:
            self.debug = debug

        # SDP voters/balances are stored as CardTransfers, so they can be easily retrieved with PeerAsset standard methods.
        if self.deck.sdp_deckid:
            # self.sdp_deck = deck_from_tx(self.deck.sdp_deckid, self.provider)
            # TODO: find_deck should be used but currently generates circular import.
            self.sdp_deck = pa.find_deck(provider=self.provider, key=self.deck.sdp_deckid, version=c.DECK_VERSION)
            # The SDP Decimal Diff is the difference between the number of decimals of the main token and the voting token.
            self.sdp_decimal_diff = self.deck.number_of_decimals - self.sdp_deck.number_of_decimals
        else:
            self.sdp_deck = None # we don't need this in sub_state: if the deck has no sdp_deck, then it's not using SDP.

        self.epoch = epoch
        self.epochs_with_completed_proposals = epochs_with_completed_proposals
        self.current_blockheight = current_blockheight

        if start_epoch is None:
            # prepare the loop, needed for SDP
            deckspawn_blockhash = provider.getrawtransaction(deck.id, 1)["blockhash"]
            deckspawn_block = provider.getblock(deckspawn_blockhash)["height"]
            self.start_epoch = deckspawn_block // deck.epoch_length # Epoch count is from genesis block

        else:
            self.start_epoch = start_epoch
        self.end_epoch = end_epoch

        self.startblock = self.start_epoch * self.deck.epoch_length # first block of the epoch the deck was spawned. Probably not needed.

        self.valid_cards = []

        # Notes for some attributes:
        # enabled_voters variable is calculated once per epoch, taking into account card issuances and card transfers.
        # enabled_voters are all voters with valid balances, and their balance.
        # used_issuance_tuples list joins all issuances of sender, txid, vout
        dict_items = ("proposal_states", "approved_proposals", "valid_proposals", "donation_txes", "enabled_voters")
        list_items = ("signalling_txes", "locking_txes", "voting_txes", "used_issuance_tuples", "valid_cards", "sdp_cards")

        for key in dict_items + list_items:

            if key in sub_state:
                init_value = sub_state["key"]
            elif key in dict_items:
                init_value = {}
            elif key in list_items:
                init_value = []

            self.__setattr__(key, init_value)

        if self.debug: print("PARSER: Initial cards:", len(self.initial_cards))

    def init_parser(self):
        """Bundles all on-chain extractions."""

        # Initial balance of SDP cards
        if self.sdp_deck != None:
            self.sdp_cards = self.get_sdp_cards()
        else:
            self.sdp_cards = None

        if self.debug: print("PARSER: Get proposal states ...", )
        self.proposal_states = get_proposal_states(self.provider, self.deck, self.current_blockheight, debug=self.debug)
        if self.debug: print(len(self.proposal_states), "found.")

        # We don't store the txes anymore in the ParserState, as they're already stored in the ProposalStates.
        # q is the number of txes for each category.
        if self.debug: print("PARSER: Get donation txes ...", )
        q = self.get_tracked_txes("donation")
        if self.debug: print(q, "found.")

        if self.debug: print("PARSER: Get locking txes ...", )
        q = self.get_tracked_txes("locking")
        if self.debug: print(q, "found.")

        if self.debug: print("PARSER: Get signalling txes ...", )
        q = self.get_tracked_txes("signalling")
        if self.debug: print(q, "found.")

        if self.debug: print("PARSER: Get voting txes ...", )
        q = self.get_tracked_txes("voting")
        if self.debug: print(q, "found.")

    def force_dstates(self):

        # Allows to set all states even if no card has been issued.
        # Has to be called in the moment the state is evaluated, i.e. normally at the end of the parsing process.
        for p in self.proposal_states.values():
            if self.debug_donations: print("PARSER: Setting donation states for Proposal:", p.id)

            # We must ensure process_donation_states is only called once per round, otherwise
            # Locking/DonationTransactions will not be added (because of the 1 state per donor address restriction)
            # MODIFIED. "processed" variable is now implemented, so double processing should be prevented with a simpler check.
            phase = 1 if self.epoch <= p.end_epoch else 0 # TODO: re-check this!
            if not p.processed[phase]:
                p.set_donation_states(debug=self.debug_donations, current_blockheight=self.current_blockheight)

    def get_sdp_cards(self):

        # NOTE: find_all_valid_cards does not filter out all invalid cards, only those determined by the parser type!
        # This means we need to get the balances via DeckState.
        from pypeerassets.__main__ import find_all_valid_cards

        if self.debug_voting: print("VOTING: Searching for SDP Token Cards ...")
        all_sdp_cards = list(find_all_valid_cards(self.provider, self.sdp_deck))
        valid_sdp_cards = self.remove_invalid_cards(all_sdp_cards)
        return valid_sdp_cards

    def get_sdp_balances(self):

        upper_limit = self.epoch * self.deck.epoch_length # balance at the start of the epoch.
        if self.epoch == self.start_epoch:
            if self.debug_voting: print("VOTING: Retrieving old SDP cards ...")
            lower_limit = 0
        else:
            lower_limit = (self.epoch - 1) * self.deck.epoch_length # balance at the start of the epoch.
        if self.debug_voting: print("VOTING: Blocklimit for this epoch:", upper_limit, "Epoch number:", self.epoch)
        if self.debug_voting: print("VOTING: Card blocks:", [card.blocknum for card in self.sdp_cards])

        cards = [ card for card in self.sdp_cards if (lower_limit <= card.blocknum < upper_limit) ]

        return cards

    def update_approved_proposals(self):
        # Filters proposals which were approved in the first-round-voting.
        # TODO: To boost efficiency and avoid redundant checks, one could delete all
        # already approved proposals from the original list (which should be renamed to "unchecked proposals")
        # Would also allow differentiate between unchecked and unapproved proposals.

        for pstate in self.proposal_states.values():

            if (pstate.start_epoch != self.epoch):
                continue

            pstate.initial_votes = self.get_votes(pstate, 0) ### phase added

            if self.debug_voting: print("VOTING: Votes round 1 for Proposal", pstate.id, ":", pstate.initial_votes)

            # case added: if voting round has not concluded, we 'll not mark proposal as abandoned.
            if self.current_blockheight < pstate.voting_periods[0][1]:
                continue

            if pstate.initial_votes["positive"] <= pstate.initial_votes["negative"]:
                pstate.state = "abandoned"
                continue

            # Set rounds, req_amount etc. again if a Proposal Modification was recorded.
            # When this method is called, we already know the last (and thus valid) Proposal Modification.
            if pstate.first_ptx.txid != pstate.valid_ptx.txid:
                pstate.modify(debug=self.debug_donations)

            self.approved_proposals.update({pstate.id : pstate})


    def update_valid_ending_proposals(self):
        # this function checks all proposals which end in a determinated epoch
        # valid proposals are those who are voted in round1 and round2 with _more_ than 50% (50% is not enough).
        # MODIFIED: modified_proposals no longer parameter.
        # Only checks round-2 votes.

        ending_valid_proposals = {}
        for pstate in self.approved_proposals.values():

            if (pstate.end_epoch != self.epoch):
                continue
            # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
            pstate.final_votes = self.get_votes(pstate, 1) ### phase added
            if self.debug_voting: print("VOTING: Votes round 2 for Proposal", pstate.id, ":", pstate.final_votes)
            if pstate.final_votes["positive"] <= pstate.final_votes["negative"]:
                pstate.state = "abandoned"
                continue

            ending_valid_proposals.update({pstate.first_ptx.txid : pstate})

        # if self.debug_voting: print("PARSER: Completed proposals in epoch {}: {}".format(self.epoch, ending_valid_proposals.keys()))

        if len(ending_valid_proposals) == 0:
            return

        self.epochs_with_completed_proposals += 1

        # Set the Distribution Factor (number to be multiplied with the donation/slot,
        # according to the requested amounts of all ending proposals)
        # Must be in a second loop as we need the complete list of valid proposals which end in this epoch.
        # Maybe this can still be optimized, with a special case if there is a single proposal in this epoch.

        for pstate in ending_valid_proposals.values():
            if self.debug_donations: print("PARSER: Checking proposal {} for dist factor. Blockheight: {}.".format(pstate.id, self.current_blockheight))
            if self.current_blockheight is not None and self.current_blockheight >= ((self.epoch + 1) * self.deck.epoch_length):
                if pstate.dist_factor is None:
                    pstate.set_dist_factor(ending_valid_proposals.values())
                    if self.debug_donations: print("PARSER: Setting dist_factor for proposal", pstate.id, ". Value:", pstate.dist_factor)
                    pstate.state = "completed"

        self.valid_proposals.update(ending_valid_proposals)

    def get_tracked_txes(self, tx_type, min_blockheight=None, max_blockheight=None):
        """Retrieves TrackedTransactions (except votes and proposals) for a deck from the blockchain
           and adds them to the corresponding ProposalState."""

        proposal_list = []
        tx_attr = "all_{}_txes".format(tx_type)
        txes = get_marked_txes(self.provider, self.deck.derived_p2th_address(tx_type), min_blockheight=min_blockheight, max_blockheight=max_blockheight)
        for q, rawtx in enumerate(txes):
            try:
                if tx_type == "donation":
                    tx = DonationTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                elif tx_type == "locking":
                    tx = LockingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                elif tx_type == "signalling":
                    tx = SignallingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                elif tx_type == "voting":
                    tx = VotingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)

                # The ProposalTransaction is added as an object afterwards, to simplify the op_return procesing.
                # proposal_tx = self.proposal_states[tx.proposal_txid].first_ptx
                # tx.set_proposal(proposal_tx)
                # We add the tx directly to the corresponding ProposalState.
                # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
                # When we create the first instance of the state we make a deepcopy.
                if tx.proposal_txid not in proposal_list:
                    current_state = deepcopy(self.proposal_states[tx.proposal_txid])
                    proposal_list.append(tx.proposal_txid)
                    getattr(current_state, tx_attr).append(tx)
                    self.proposal_states.update({ tx.proposal_txid : current_state })
                else:
                    current_state = self.proposal_states[tx.proposal_txid]
                    getattr(current_state, tx_attr).append(tx)

                # We keep a dictionary of DonationTransactions for better lookup from the Parser.
                if tx_type == "donation":
                    self.donation_txes.update({tx.txid : tx})

            except (InvalidTrackedTransactionError, KeyError):
                continue
        try:
            return q
        except UnboundLocalError: # if no txes were found
            return 0

    def get_votes(self, proposal, phase, formatted_result=False):
        # TODO should be integrated in the ProposalState class.
        # returns a dictionary with two keys: "positive" and "negative",
        # containing the amounts of the tokens with whose address a proposal was voted.
        # NOTE: The balances are valid for the epoch of the ParserState. So this cannot be called
        #       for votes in other epochs.
        # NOTE 2: In this protocol the last vote counts (this is why the vtxs list is reversed).
        #       You can always change you vote.
        # TODO: This is still without the "first vote can also be valid for second round" system.
        # Formatted_result returns the "decimal" value of the votes, i.e. the number of "tokens"
        # which voted for the proposal, which depends on the "number_of_decimals" value.
        # MODIFIED: This is now called by phase, it is more transparent and efficient.

        votes = {}
        voters = [] # to filter out duplicates.
        debug = self.debug_voting

        if debug: print("VOTING: Enabled Voters:", self.enabled_voters)

        votes = { "negative" : 0, "positive" : 0 }
        if len(proposal.all_voting_txes) == 0:
            return votes

        ### FIX 1 ### (try to do it more elegant later)
        if phase == 0:
            phase_vtxes = [ v for v in proposal.all_voting_txes if v.epoch == proposal.start_epoch ]
        elif phase == 1:
            phase_vtxes = [ v for v in proposal.all_voting_txes if v.epoch == proposal.end_epoch ]
        # sorted_vtxes = sorted(proposal.all_voting_txes, key=lambda tx: tx.blockheight, reverse=True)
        sorted_vtxes = sorted(phase_vtxes, key=lambda tx: tx.blockheight, reverse=True)

        for v in sorted_vtxes: # reversed for the "last vote counts" rule.
            if debug: print("VOTING: Vote: Epoch", v.epoch, "txid:", v.txid, "sender:", v.sender, "outcome:", v.vote, "height", v.blockheight)
            if (v.epoch == self.epoch) and (v.sender not in voters):
                try:
                    if debug: print("VOTING: Vote is valid.")
                    voter_balance = self.enabled_voters[v.sender] # voting token balance at start of epoch
                    if debug: print("VOTING: Voter balance", voter_balance)
                    vote_outcome = "positive" if v.vote == b'+' else "negative"
                    votes[vote_outcome] += voter_balance
                    if debug: print("VOTING: Balance of outcome", vote_outcome, "increased by", voter_balance)
                    voters.append(v.sender)

                    # set the weight in the transaction (vote_weight attribute)
                    v.set_weight(voter_balance)

                    # Valid voting txes are appended to ProposalStates.voting_txes by round and outcome
                    proposal.voting_txes[phase].append(v)

                except KeyError: # will always be thrown if a voter is not enabled in the "current" epoch.
                    if debug: print("VOTING: Voter has no balance in the current epoch.")
                    continue

            elif v.epoch < self.epoch: # due to it being sorted we can cut off all txes before the relevant epoch.
                break ### maybe not more necessary due to phase addition!

        if formatted_result:
            for outcome in ("positive", "negative"):
                balance = Decimal(votes[outcome]) / 10 ** self.deck.number_of_decimals
                # modified: base is number_of_decimals of main deck. old version:
                # balance = Decimal(votes[outcome]) / 10**self.sdp_deck.number_of_decimals

                votes.update({outcome : balance})

        return votes

    def validate_proposer_issuance(self, dtx_id, card_units, card_sender, card_blocknum):

        debug = self.debug_donations
        proposal_state = self.valid_proposals[dtx_id] # checked just before the call, so no "try/except" necessary.

        if debug: print("PARSER: Checking Proposer issuance based on proposal", proposal_state.id)
        # 1. Check if the card issuer is identical to the Proposer.
        if card_sender not in proposal_state.valid_ptx.input_addresses:
            if debug: print("PARSER: Proposer issuance failed: Incorrect card issuer.")
            return False

        # 2. Card must be issued after the last round deadline. Otherwise, a card could be valid for a couple of blocks,
        # and then become invalid.
        # TODO this may be innecessary, as this is valid for all issuances, not only Proposer issuances.
        # But check first if there are different checks in donation issuances.
        try:
           # MODIFIED: as the Proposer round is not longer necessary, modified [8][0][0] to [7][1][1] + 1
           last_round_end = proposal_state.rounds[7][1][1] + 1 # modified from round_starts
        except (IndexError, AttributeError):
           # if rounds attribute is still not set , e.g. because there was not a single Donation CardIssue.
           # then we set rounds. Should normally not be necessary, as rounds is now finalized in update_approved_proposals.
           proposal_state.set_rounds()
           last_round_end = proposal_state.rounds[7][1][1] + 1

        if card_blocknum < last_round_end:
            if debug: print("PARSER: Proposer issuance failed: card issued before end epoch of ProposalState.")
            return False

        if len(proposal_state.donation_states) == 0:
            proposal_state.set_donation_states()

        if card_units != proposal_state.proposer_reward:
            if debug: print("PARSER: Proposer issuance failed: Incorrect amount.")
            return False

        return True

    def validate_donation_issuance(self, dtx_id, dtx_vout, card_units, card_sender):

        """Main validation function for donations. Checks for each issuance if the donation was correct.
        The donation transaction ID is provided (by the issue transaction)
        and it is checked if it corresponds to a real donation."""

        # Possible improvement: raise exceptions instead of simply returning False?
        debug = self.debug_donations

        if debug: print("PARSER: Checking CardIssue based on donation tx:", dtx_id)

        # check A: does proposal exist?
        if debug: print("PARSER: Valid proposals:", self.valid_proposals)

        # MODIFIED: for now we use a dict for the DonationTransaction objects, so they can be called fastly.
        # TODO: the ProposalState check could perhaps be eliminated if we ensure the DTXes here are valid.
        try:
            dtx = self.donation_txes[dtx_id]
            if debug: print("PARSER: Donation transaction found.")
        except KeyError:
            if debug: print("PARSER: Donation issue failed: Transaction not found or not valid.")
            return False

        try:
            proposal_state = self.valid_proposals[str(dtx.proposal_txid)]
        except KeyError:
            if debug: print("PARSER: Proposal state does not exist or was not approved.")
            return False

        # We only associate donation/signalling txes to Proposals which really correspond to a card (token unit[s]) issued.
        # This way, fake/no participation proposals and donations with no associated card issue attempts are ignored,
        # which could be a way to attack the system with spam.

        if len(proposal_state.donation_states) == 0:
            if debug: print("PARSER: Creating donation states ...")
            proposal_state.set_donation_states(debug=self.debug_donations)

        if debug: print("PARSER: Number of donation txes:", len([tx for r in proposal_state.donation_txes for tx in r ]))

        # check B: Does txid correspond to a real donation?
        # We go through the DonationStates per round and search for the dtx_id.
        # When we find it, we get the DonationState for the card issuance.
        dstates = [d for rd_states in proposal_state.donation_states for d in rd_states.values()]
        for ds in dstates:
            if ds.donation_tx is not None:
                # if debug: print("PARSER: Checking donation state:", ds.id, "with donation tx", ds.donation_tx.txid)
                if ds.donation_tx.txid == dtx_id:
                    break
            #else:
                #continue
        else:
            if debug: print("PARSER: Donation issuance failed: No matching donation state found.")
            return False

        # Check C: The card issuance transaction was signed really by the donor?
        if card_sender != ds.donor_address:
            if debug: print("PARSER: Donation issuance failed: Card sender {} not corresponding to donor address {}".format(card_sender, ds.donor_address))
            return False

        if debug: print("PARSER: Initial slot:", ds.slot, "Effective slot:", ds.effective_slot)
        if debug: print("PARSER: Real donation", ds.donated_amount)
        if debug: print("PARSER: Card amount:", card_units)
        if debug: print("PARSER: Calculated reward:", ds.reward)
        if debug: print("PARSER: Distribution Factor", proposal_state.dist_factor)


        # Check D: Was the issued amount correct?
        if card_units != ds.reward:
            if debug: print("PARSER: Donation issuance failed: Incorrect issued token amount, different from the assigned slot.")
            return False
        else:
            return True

    @staticmethod
    def remove_invalid_cards(cards):
        from pypeerassets.protocol import DeckState
        # this function filters out ALL invalid cards. It uses the DeckState from PeerAssets with a slight modification.
        state = DeckState(cards)
        return state.valid_cards


    def check_card(self, card):
        """Checks a CardIssue for validity. CardTransfers are always valid (they will be later processed by DeckState)."""

        # NOTE: this replaced get_valid_epoch_cards, as it's also be compatible with a generator-based approach.
        # CONVENTION: voters' weight is the balance at the start block of current epoch

        debug = self.debug_donations
        # card_data = card.asset_specific_data # not needed anymore due to PROTOBUF

        if card.type == "CardIssue":
            if debug: print("PARSER: Checking validity of CardIssue", card.txid, "based on txid:", card.donation_txid)

            # First step: Look for a matching DonationTransaction.
            dtx_id = card.donation_txid

            # dtx_vout should currently always be 2. However, the variable is kept for future modifications.
            # dtx_vout_bytes = getfmt(card_data, CARD_ISSUE_DT_FORMAT, "out")
            # dtx_vout = int.from_bytes(dtx_vout_bytes, "big")
            # dtx_vout = card.extended_data.vout ### PROTOBUF
            dtx_vout = card.donation_vout # MODIF: has now a proper attribute.

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, dtx_id, dtx_vout) in self.used_issuance_tuples:
                if debug: print("PARSER: Ignoring CardIssue: Duplicate.")
                return False

            card_units = sum(card.amount) # MODIFIED: this is already an int value based on the card base units

            # Check if it is a proposer or a donation issuance.
            # Proposers provide the ref_txid of their proposal transaction.
            # If this TX is in proposal_txes and they are the sender of the card and fulfill all requirements,
            # then the token is granted to them at their proposal address.

            if (dtx_id in self.valid_proposals) and self.validate_proposer_issuance(dtx_id, card_units, card.sender, card.blocknum):
                if debug: print("PARSER: DT CardIssue (Proposer):", card.txid)

            elif self.validate_donation_issuance(dtx_id, dtx_vout, card_units, card.sender):
                if debug: print("PARSER: DT CardIssue (Donation):", card.txid)

            else:
                if debug: print("PARSER: Ignoring CardIssue: Invalid data.")
                return False

            self.used_issuance_tuples.append((card.sender, dtx_id, dtx_vout))
            return True

        else:

            if debug: print("PARSER: DT CardTransfer:", card.txid)
            return True

    def epoch_init(self):
        # EXPERIMENTAL, new parser structure without position lookup.
        # This is called when the card loop enters a new epoch.
        debug = self.debug_voting

        epoch_firstblock, epoch_lastblock = self.epoch * self.deck.epoch_length, (self.epoch + 1) * self.deck.epoch_length - 1
        if debug: print("PARSER: Checking epoch:", self.epoch, ", from block", epoch_firstblock, "to", epoch_lastblock)

        if self.deck.sdp_periods: # should give true if 0 or None

            sdp_epochs_remaining = self.deck.sdp_periods - self.epochs_with_completed_proposals

            if debug: print("VOTING: Epochs with completed proposals:", self.epochs_with_completed_proposals)
            if debug: print("VOTING: SDP periods remaining:", sdp_epochs_remaining)

            #if (self.deck.sdp_periods > 0) and (sdp_epochs_remaining <= self.deck.sdp_periods): # voters from other tokens
            if sdp_epochs_remaining <= self.deck.sdp_periods:

                # We set apart all CardTransfers of SDP voters before the epoch start
                sdp_epoch_balances = self.get_sdp_balances()

                # Weight is calculated according to the epoch
                # Weight is reduced only in epochs where proposals were completely approved.
                sdp_weight = get_sdp_weight(self.epochs_with_completed_proposals, self.deck.sdp_periods)

                # Adjusted weight multiplies the token balance by the difference in decimal places
                # between the main token and the SDP token.
                # adjusted_weight = sdp_weight * 10 ** self.sdp_decimal_diff

                if len(sdp_epoch_balances) > 0:
                    updated_sdp_voters = update_voters(self.enabled_voters, sdp_epoch_balances, weight=sdp_weight, debug=self.debug_voting, dec_diff=self.sdp_decimal_diff)
                    self.enabled_voters.update(updated_sdp_voters)

        # As card issues can occur any time after the proposal has been voted
        # we always need to process all valid proposals voted up to this epoch.

        if debug: print("VOTING: Get ending proposals ...")

        self.update_approved_proposals()
        if debug: print("VOTING: Approved proposals after epoch", self.epoch, list(self.approved_proposals.keys()))

        self.update_valid_ending_proposals()
        if debug: print("VOTING: Valid ending proposals after epoch:", self.epoch, list(self.valid_proposals.keys()))


    def epoch_postprocess(self, valid_epoch_cards):
        # if debug: print("Valid cards found in this epoch:", len(valid_epoch_cards))

        self.enabled_voters.update(update_voters(voters=self.enabled_voters, new_cards=valid_epoch_cards, debug=self.debug_voting))
        # if debug: print("New voters balances:", self.enabled_voters)

        # if it's integrated into DeckState we probably don't need this, as we have DeckState.valid_cards
        self.valid_cards += valid_epoch_cards


    def process_cardless_epochs(self, start, end):

        for epoch in range(start, end + 1):
            self.epoch = epoch
            self.epoch_init()
            self.epoch == epoch
            # the postprocess step can be skipped, as there are no cards.
        self.epoch += 1 # TODO re-check! This sets the epoch to the one where the card is.


