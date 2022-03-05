""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch, instead by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.transaction_formats import *
from pypeerassets.at.dt_parser_utils import *

class ParserState(object):
    """A ParserState contains the current state of all important variables for a single deck."""
    # TODO: we need to evaluate where to use DeckState in the parser.

    def __init__(self, deck, initial_cards, provider, proposal_states={}, approved_proposals={}, valid_proposals={}, signalling_txes=[], locking_txes=[], donation_txes={}, voting_txes=[], epoch=None, start_epoch=None, end_epoch=None, used_issuance_tuples=[], valid_cards=[], enabled_voters={}, sdp_cards=[], sdp_deck=None, current_blockheight=None, epochs_with_completed_proposals=0, debug=False):

        self.deck = deck
        self.initial_cards = initial_cards
        self.provider = provider
        self.current_blockheight = current_blockheight

        self.valid_cards = valid_cards
        self.proposal_states = proposal_states
        self.approved_proposals = approved_proposals # approved by round 1 votes
        self.valid_proposals = valid_proposals # successfully completed: approved by round 1 + 2 votes
        self.donation_txes = donation_txes # MODIFIED as a dict!
        self.voting_txes = voting_txes # this is a dict, not list.
        self.epochs_with_completed_proposals = epochs_with_completed_proposals

        # enabled_voters variable is calculated once per epoch, taking into account card issuances and card transfers.
        # enabled_voters are all voters with valid balances, and their balance.
        self.enabled_voters = enabled_voters
        # SDP voters/balances are stored as CardTransfers, so they can be easily retrieved with PeerAsset standard methods.
        if self.deck.sdp_deckid:
            self.sdp_deck = deck_from_tx(self.deck.sdp_deckid, self.provider)
        else:
            self.sdp_deck = sdp_deck
        self.sdp_cards = sdp_cards
        # The SDP Decimal Diff is the difference between the number of decimals of the main token and the voting token.
        self.sdp_decimal_diff = self.deck.number_of_decimals - self.sdp_deck.number_of_decimals


        # used_issuance_tuples list joins all issuances of sender, txid, vout:
        self.used_issuance_tuples = used_issuance_tuples

        self.epoch = epoch

        if not start_epoch:
            # prepare the loop, needed for SDP
            deckspawn_blockhash = provider.getrawtransaction(deck.id, 1)["blockhash"]
            deckspawn_block = provider.getblock(deckspawn_blockhash)["height"]
            self.start_epoch = deckspawn_block // deck.epoch_length # Epoch count is from genesis block

        else:
            self.start_epoch = start_epoch
        self.end_epoch = end_epoch

        self.startblock = self.start_epoch * self.deck.epoch_length # first block of the epoch the deck was spawned. Probably not needed.
        self.debug = debug # print statements for debugging

    def init_parser(self):
        """Bundles all on-chain extractions."""

        # Initial balance of SDP cards
        if self.sdp_deck != None:
            self.sdp_cards = self.get_sdp_cards()
        else:
            self.sdp_cards = None

        if self.debug: print("Get proposal states ...", )
        self.proposal_states = get_proposal_states(self.provider, self.deck, self.current_blockheight)
        if self.debug: print(len(self.proposal_states), "found.")

        # We don't store the txes anymore in the ParserState, as they're already stored in the ProposalStates.
        # q is the number of txes for each category.
        if self.debug: print("Get donation txes ...", )
        q = self.get_tracked_txes("donation")
        if self.debug: print(q, "found.")

        if self.debug: print("Get locking txes ...", )
        q = self.get_tracked_txes("locking")
        if self.debug: print(q, "found.")

        if self.debug: print("Get signalling txes ...", )
        q = self.get_tracked_txes("signalling")
        if self.debug: print(q, "found.")

        if self.debug: print("Get voting txes ...", )
        self.get_voting_txes()
        if self.debug: print(len(self.voting_txes), "proposals with voting transactions found.")

    def force_dstates(self):
        # Allows to set all states even if no card has been issued.
        # Has to be called in the moment the state is evaluated, i.e. normally at the end of the parsing process.
        for p in self.proposal_states.values():
            if self.debug: print("Setting donation states for Proposal:", p.id)

            # We must ensure process_donation_states is only called once per round, otherwise
            # Locking/DonationTransactions will not be added (because of the 1 state per donor address restriction)
            # MODIFIED. "processed" variable is now implemented, so double processing should be prevented with a simpler check.
            phase = 1 if self.epoch <= p.end_epoch else 0 # TODO: re-check this!
            if not p.processed[phase]:
                p.set_donation_states(debug=self.debug, current_blockheight=self.current_blockheight)

            # Explanation: In the case the method is called after the end_epoch, it sets the donation states only
            # if there was no single donation state set for the last 4 rounds.
            # This is still "hacky". It will prevent double processing of states, but not prevent to call the method
            # twice, for example if there are no donation states in rounds 4-7.
            # phase 2 is necessary to guarantee the processing is complete, as phase 1 is in an earlier epoch.
            #if self.epoch <= p.end_epoch:
            #    dstates_rounds = p.donation_states
            #else:
            #    dstates_rounds = p.donation_states[4:]
            #processed_dstates = [s for r in dstates_rounds for s in r.keys()]
            # print("Processed dstates for proposal", p.id, processed_dstates, "rds:", len(dstates_rounds))
            #if len(processed_dstates) == 0:
            #    p.set_donation_states(debug=self.debug, current_blockheight=self.current_blockheight)

    def get_sdp_cards(self):
        # NOTE: this does NOT filter out all invalid cards, only those determined by the parser type!
        # This means we need to get the balances via DeckState.
        from pypeerassets.__main__ import find_all_valid_cards
        if self.debug: print("Searching for SDP Token Cards ...")
        all_cards = list(find_all_valid_cards(self.provider, self.sdp_deck))
        valid_cards = self.remove_invalid_cards(all_cards)
        return valid_cards

    def get_sdp_balances(self):
        upper_limit = self.epoch * self.deck.epoch_length # balance at the start of the epoch.
        if self.epoch == self.start_epoch:
            if self.debug: print("Retrieving old cards ...")
            lower_limit = 0
        else:
            lower_limit = (self.epoch - 1) * self.deck.epoch_length # balance at the start of the epoch.
        if self.debug: print("Blocklimit for this epoch:", upper_limit, "Epoch number:", self.epoch)
        if self.debug: print("Card blocks:", [card.blocknum for card in self.sdp_cards])

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

            pstate.initial_votes = self.get_votes(pstate)
            if self.debug: print("Votes round 1 for Proposal", pstate.id, ":", pstate.initial_votes)

            if pstate.initial_votes["positive"] <= pstate.initial_votes["negative"]:
                pstate.state = "abandoned"
                continue

            # Set rounds, req_amount etc. again if a Proposal Modification was recorded.
            # When this method is called, we already know the last (and thus valid) Proposal Modification.
            if pstate.first_ptx.txid != pstate.valid_ptx.txid:
                pstate.modify()

            self.approved_proposals.update({pstate.id : pstate})


    def update_valid_ending_proposals(self):
        # this function checks all proposals which end in a determinated epoch
        # valid proposals are those who are voted in round1 and round2 with _more_ than 50% (50% is not enough).
        # MODIFIED: modified_proposals no longer parameter.
        # Only checks round-2 votes.

        ending_valid_proposals = {}
        for pstate in self.approved_proposals.values():
            if self.debug: print("Checking end epoch for completed proposals:", pstate.end_epoch)
            if (pstate.end_epoch != self.epoch):
                continue
            # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
            pstate.final_votes = self.get_votes(pstate)
            if self.debug: print("Votes round 2 for Proposal", pstate.id, ":", pstate.final_votes)
            if pstate.final_votes["positive"] <= pstate.final_votes["negative"]:
                pstate.state = "abandoned"
                continue

            ending_valid_proposals.update({pstate.first_ptx.txid : pstate})

        if len(ending_valid_proposals) == 0:
            return

        self.epochs_with_completed_proposals += 1

        # Set the Distribution Factor (number to be multiplied with the donation/slot,
        # according to the requested amounts of all ending proposals)
        # Must be in a second loop as we need the complete list of valid proposals which end in this epoch.
        # Maybe this can still be optimized, with a special case if there is a single proposal in this epoch.

        for pstate in ending_valid_proposals.values():
            if self.current_blockheight is not None and self.current_blockheight >= ((self.epoch + 1) * self.deck.epoch_length):
                if pstate.dist_factor is None:
                    pstate.set_dist_factor(ending_valid_proposals.values())
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

                # The ProposalTransaction is added as an object afterwards, to simplify the op_return procesing.
                proposal_tx = self.proposal_states[tx.proposal_txid].first_ptx
                tx.set_proposal(proposal_tx)
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
                    # current_state.all_donation_txes.append(tx)

                # We keep a dictionary of DonationTransactions for better lookup from the Parser.
                if tx_type == "donation":
                    self.donation_txes.update({tx.txid : tx})

            except (InvalidTrackedTransactionError, KeyError):
                continue
        try:
            return q
        except UnboundLocalError: # if no txes were found
            return 0

    def get_votes(self, proposal, formatted_result=False):
        # TODO if it works it should be integrated in the ProposalState class.
        # returns a dictionary with two keys: "positive" and "negative",
        # containing the amounts of the tokens with whose address a proposal was voted.
        # NOTE: The balances are valid for the epoch of the ParserState. So this cannot be called
        #       for votes in other epochs.
        # NOTE 2: In this protocol the last vote counts (this is why the vtxs list is reversed).
        #       You can always change you vote.
        # TODO: This is still without the "first vote can also be valid for second round" system.
        # Formatted_result returns the "decimal" value of the votes, i.e. the number of "tokens"
        # which voted for the proposal, which depends on the "number_of_decimals" value.

        votes = {}
        voters = [] # to filter out duplicates.
        debug = self.debug

        if debug: print("Enabled Voters:", self.enabled_voters)

        votes = { "negative" : 0, "positive" : 0 }
        if len(proposal.all_voting_txes) == 0:
            return votes

        sorted_vtxes = sorted(proposal.all_voting_txes, key=lambda tx: tx.blockheight, reverse=True)

        for v in sorted_vtxes: # reversed for the "last vote counts" rule.
            if debug: print("Vote: Epoch", v.epoch, "txid:", v.txid, "sender:", v.sender, "outcome:", v.vote, "height", v.blockheight)
            if (v.epoch == self.epoch) and (v.sender not in voters):
                try:
                    if debug: print("Vote is valid.")
                    voter_balance = self.enabled_voters[v.sender] # voting token balance at start of epoch
                    if debug: print("Voter balance", voter_balance)
                    vote_outcome = "positive" if v.vote == b'+' else "negative"
                    votes[vote_outcome] += voter_balance
                    if debug: print("Balance of outcome", vote_outcome, "increased by", voter_balance)
                    voters.append(v.sender)

                    # set the weight in the transaction (vote_weight attribute)
                    v.set_weight(voter_balance)

                    # Valid voting txes are appended to ProposalStates.voting_txes by round and outcome
                    if v.epoch == proposal.start_epoch:
                        proposal.voting_txes[0].append(v)
                    elif v.epoch == proposal.end_epoch:
                        proposal.voting_txes[1].append(v)

                except KeyError: # will always be thrown if a voter is not enabled in the "current" epoch.
                    if debug: print("Voter has no balance in the current epoch.")
                    continue

            elif v.epoch < self.epoch: # due to it being sorted we can cut off all txes before the relevant epoch.
                break

        if formatted_result:
            for outcome in ("positive", "negative"):
                balance = Decimal(votes[outcome]) / 10 ** self.deck.number_of_decimals
                # modified: base is number_of_decimals of main deck. old version:
                # balance = Decimal(votes[outcome]) / 10**self.sdp_deck.number_of_decimals

                votes.update({outcome : balance})

        return votes

    def get_voting_txes(self, min_blockheight=None, max_blockheight=None):
        # gets ALL voting txes of a deck. Needs P2TH.
        # MODIFIED: Votes now get stored along the ProposalState, not the ParserState.
        # uses a dict to group votes by proposal and by outcome ("positive" and "negative")
        # b'+' is the value for a positive vote, b'-' is negative, others are invalid.
        outcome_options = { b'+' : "positive", b'-' : "negative" }

        for rawtx in get_marked_txes(self.provider, self.deck.derived_p2th_address("voting"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):

            try:
                tx = VotingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                outcome = outcome_options[tx.vote]
            except (KeyError, InvalidTrackedTransactionError):
                continue

            # The ProposalTransaction is added as an object afterwards, to simplify the op_return procesing.
            proposal_state = self.proposal_states[tx.proposal_txid]
            proposal_tx = proposal_state.first_ptx
            tx.set_proposal(proposal_tx)
            proposal_txid = tx.proposal.txid

            proposal_state.all_voting_txes.append(tx)


    def validate_proposer_issuance(self, dtx_id, card_units, card_sender, card_blocknum):

        debuf = self.debug
        proposal_state = self.valid_proposals[dtx_id] # checked just before the call, so no "try/except" necessary.

        # 1. Check if the card issuer is identical to the Proposer.
        if card_sender not in proposal_state.valid_ptx.input_addresses:
            if debug: print("Proposer issuance failed: Incorrect card issuer.")
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
            return False

        if len(proposal_state.donation_states) == 0:
            proposal_state.set_donation_states()

        if card_units != proposal_state.proposer_reward:
            return False

        return True

    def validate_donation_issuance(self, dtx_id, dtx_vout, card_units, card_sender):

        """Main validation function for donations. Checks for each issuance if the donation was correct.
        The donation transaction ID is provided (by the issue transaction)
        and it is checked if it corresponds to a real donation."""

        # Possible improvement: raise exceptions instead of simply returning False?
        debug = self.debug

        if debug: print("Checking donation tx:", dtx_id)

        # check A: does proposal exist?
        if debug: print("Valid proposals:", self.valid_proposals)

        # MODIFIED: for now we use a dict for the DonationTransaction objects, so they can be called fastly.
        try:
            dtx = self.donation_txes[dtx_id]
        except KeyError:
            if self.debug: print("Donation transaction not found or not valid.")
            return False

        try:
            proposal_state = self.valid_proposals[str(dtx.proposal_txid)]
        except KeyError:
            if self.debug: print("Proposal state does not exist or was not approved.")
            return False

        # We only associate donation/signalling txes to Proposals which really correspond to a card (token unit[s]) issued.
        # This way, fake/no participation proposals and donations with no associated card issue attempts are ignored,
        # which could be a way to attack the system with spam.

        if len(proposal_state.donation_states) == 0:
            proposal_state.set_donation_states(debug=self.debug)

        if debug: print("Number of donation txes:", len([tx for r in proposal_state.donation_txes for tx in r ]))

        # check B: Does txid correspond to a real donation?
        # We go through the DonationStates per round and search for the dtx_id.
        # When we find it, we get the DonationState for the card issuance.
        for rd_states in proposal_state.donation_states:
            for ds in rd_states.values():
                if (ds.donation_tx is not None) and (ds.donation_tx.txid == dtx_id):
                    break
                else:
                    continue
            break

        # Check C: The card issuance transaction was signed really by the donor?
        if card_sender != ds.donor_address:
            return False

        if debug: print("Initial slot:", ds.slot, "Effective slot:", ds.effective_slot)
        if debug: print("Real donation", ds.donated_amount)
        if debug: print("Card amount:", card_units)
        if debug: print("Calculated reward:", ds.reward)
        if debug: print("Distribution Factor", proposal_state.dist_factor)


        # Check D: Was the issued amount correct?
        if card_units != ds.reward:
            if debug: print("Incorrect issued token amount, different from the assigned slot.")
            return False
        else:
            return True

    def get_valid_epoch_cards(self, epoch_cards):

        # This is the loop which checks all cards in an epoch for validity.
        # It loops, in each epoch, through the current issuances and checks if they're associated to a valid donation.
        # CONVENTION: voters' weight is the balance at the start block of current epoch

        debug = self.debug
        valid_cards = []

        if debug: print("Cards:", [card.txid for card in epoch_cards])

        for card in epoch_cards:

            card_data = card.asset_specific_data

            if card.type == "CardIssue":

                # First step: Look for a matching DonationTransaction.
                dtx_id = card.donation_txid

                # dtx_vout should currently always be 2. However, the variable is kept for future modifications.
                dtx_vout_bytes = getfmt(card_data, CARD_ISSUE_DT_FORMAT, "out")
                dtx_vout = int.from_bytes(dtx_vout_bytes, "big")

                # check 1: filter out duplicates (less expensive, so done first)
                if (card.sender, dtx_id, dtx_vout) in self.used_issuance_tuples:
                    if debug: print("Ignoring CardIssue: Duplicate.")
                    continue

                card_units = sum(card.amount) # MODIFIED: this is already an int value based on the card base units!

                # Is it a proposer or a donation issuance?
                # Proposers provide ref_txid of their proposal transaction.
                # If this TX is in proposal_txes, AND they are the sender of the card and fulfill all requirements,
                # then they get the token to the proposal address.

                if (dtx_id in self.valid_proposals) and self.validate_proposer_issuance(dtx_id, card_units, card.sender, card.blocknum):
                    if debug: print("DT CardIssue (Proposer):", card.txid)
                elif self.validate_donation_issuance(dtx_id, dtx_vout, card_units, card.sender):
                    if debug: print("DT CardIssue (Donation):", card.txid)
                else:
                    if debug: print("Ignoring CardIssue: Invalid data.")
                    continue

                valid_cards.append(card) # Cards of all types are returned chronologically.
                self.used_issuance_tuples.append((card.sender, dtx_id, dtx_vout))

            else:

                if debug: print("DT CardTransfer:", card.txid)
                valid_cards.append(card)

        return valid_cards

    @staticmethod
    def remove_invalid_cards(cards):
        from pypeerassets.protocol import DeckState
        # this function filters out ALL invalid cards. It uses the DeckState from PeerAssets with a slight modification.
        state = DeckState(cards)
        return state.valid_cards




