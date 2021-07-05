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
    """contains the current state of basic variables"""

    def __init__(self, deck, initial_cards, provider, proposal_states={}, approved_proposals={}, valid_proposals={}, signalling_txes=[], locking_txes=[], donation_txes={}, voting_txes=[], epoch=None, start_epoch=None, end_epoch=None, used_issuance_tuples=[], valid_cards=[], enabled_voters={}, sdp_cards=[], sdp_deck=None, current_blockheight=None, epochs_with_completed_proposals=0, debug=False):

        self.deck = deck
        self.initial_cards = initial_cards
        self.provider = provider
        self.current_blockheight = current_blockheight

        self.valid_cards = valid_cards
        self.proposal_states = proposal_states
        self.approved_proposals = approved_proposals # approved by round 1 votes
        self.valid_proposals = valid_proposals # successfully completed: approved by round 1 + 2 votes 
        # self.signalling_txes = signalling_txes # TODO: PROBABLY obsolete!
        # self.locking_txes = locking_txes # TODO: probably obsolete!
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
        #self.proposal_states = get_proposal_states(self.provider, self.deck, self.current_blockheight, self.signalling_txes, self.donation_txes) # TODO: re-ckech if the last params are necessary!
        self.proposal_states = get_proposal_states(self.provider, self.deck, self.current_blockheight)
        if self.debug: print(len(self.proposal_states), "found.")

        # We don't store the txes anymore here, as they're already stored in the ProposalStates.
        # q is the number of txes for each category.
        if self.debug: print("Get donation txes ...", )

        # q = get_donation_txes(self.provider, self.deck, self)
        q = self.get_tracked_txes("donation")
        if self.debug: print(q, "found.")

        if self.debug: print("Get locking txes ...", )
        q = self.get_tracked_txes("locking")
        # q = get_locking_txes(self.provider, self.deck, self)
        if self.debug: print(q, "found.")

        if self.debug: print("Get signalling txes ...", )
        q = self.get_tracked_txes("signalling")

        # q = get_signalling_txes(self.provider, self.deck, self)
        if self.debug: print(q, "found.")

        if self.debug: print("Get voting txes ...", )
        self.voting_txes = self.get_voting_txes()
        if self.debug: print(len(self.voting_txes), "proposal with voting transactions found.")

    def force_dstates(self):
        # Allows to set all states even if no card has been issued. # TODO: Check epochs.
        # Has to be called in the moment the state is evaluated, i.e. normally at the end of the parsing process.
        for p in self.proposal_states.values():
            if self.debug: print("Setting donation states for Proposal:", p.first_ptx.txid)

            # We must ensure process_donation_states is only called once per round,
            # otherwise Locking/Donation Transactions will not be added (because of the donor address restriction)
            # TODO: this is still "hacky". It will prevent double processing of states, but not calling the method
            # twice, for example if there are no donation states in rounds 4-7.
            # phase 2 is necessary to guarantee the processing is complete, as phase 1 is in an earlier epoch.
            # maybe it is easier to add a "processed" variable to ProposalState? (with the processed phase)
            if self.epoch <= p.end_epoch:
                dstates_rounds = p.donation_states
            else:
                dstates_rounds = p.donation_states[4:]
            if len([s for r in dstates_rounds for s in r.keys()]) == 0:
                p.set_donation_states(debug=self.debug, current_blockheight=self.current_blockheight)

    def get_sdp_cards(self):
        from pypeerassets.__main__ import find_all_valid_cards
        if self.debug: print("Searching for SDP Token Cards ...")
        return list(find_all_valid_cards(self.provider, self.sdp_deck))

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
        # already approved proposals from the original list (which should be re-branded to "unchecked proposals")
        # Would also allow differentiate between unchecked and unapproved proposals.

        for pstate in self.proposal_states.values():

            if (pstate.start_epoch != self.epoch):
                continue

            pstate.initial_votes = self.get_votes(pstate)
            if self.debug: print("Votes round 1 for Proposal", pstate.first_ptx.txid, ":", pstate.initial_votes)

            if pstate.initial_votes["positive"] <= pstate.initial_votes["negative"]:
                # MODIFIED: State is set to abandoned.
                pstate.state = "abandoned"
                continue

            self.approved_proposals.update({pstate.first_ptx.txid : pstate})


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
            if self.debug: print("Votes round 2 for Proposal", pstate.first_ptx.txid, ":", pstate.final_votes)
            if pstate.final_votes["positive"] <= pstate.final_votes["negative"]:
                pstate.state = "abandoned"
                continue

            ending_valid_proposals.update({pstate.first_ptx.txid : pstate})

        if len(ending_valid_proposals) == 0:
            return

        self.epochs_with_completed_proposals += 1
    
        # Set the Distribution Factor (number to be multiplied with the donation/slot, according to proposals and token amount)
        # Must be in a second loop as we need the complete list of valid proposals which end in this epoch.
        # Maybe this can still be optimized, with a special case if there is a single proposal in this epoch.
        # TODO: Should be probably a separate method. Would also allow to do the round checks in the same method for rd1 and 2.

        for pstate in ending_valid_proposals.values():
            if self.current_blockheight is not None and self.current_blockheight >= ((self.epoch + 1) * self.deck.epoch_length):
                if pstate.dist_factor is None:
                    pstate.set_dist_factor(ending_valid_proposals.values())
                    pstate.state = "completed"

        self.valid_proposals.update(ending_valid_proposals)


    def get_votes(self, proposal, formatted_result=False):
        # returns a dictionary with two keys: "positive" and "negative",
        # containing the amounts of the tokens with whom an address was voted.
        # NOTE: The balances are valid for the epoch of the ParserState. So this cannot be called
        #       for votes in other epochs.
        # NOTE 2: In this protocol the last vote counts (this is why the vtxs list is reversed).
        #       You can always change you vote.
        # TODO: This is still without the "first vote can also be valid for second round" system.
        # Formatted_result returns the "decimal" value of the votes, i.e. the number of "tokens"
        # which voted for the proposal, which depends on the "number_of_decimals" value.
        # TODO: ProposalState should have attributes to show every single vote and their balances (at least optional, for the pacli commands).

        votes = {}
        voters = [] # to filter out duplicates.
        debug = self.debug

        if debug: print("Enabled Voters:", self.enabled_voters)
        try:
            vtxes_proposal = self.voting_txes[proposal.first_ptx.txid]
        except KeyError: # gets thrown if the proposal was not added to self.voting_txes, i.e. when no votes were found.
            return {"positive" : 0, "negative" : 0}

        voting_txes = []
        for outcome in ("positive", "negative"):
            if outcome in vtxes_proposal:
                voting_txes += vtxes_proposal.get(outcome)

        sorted_vtxes = sorted(voting_txes, key=lambda tx: tx.blockheight, reverse=True)
    
        votes = { "negative" : 0, "positive" : 0 }

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

    def get_tracked_txes(self, tx_type, min_blockheight=None, max_blockheight=None):
        # MODIFIED: simplification of get_donation_txes etc.
        # gets ALL donation txes of a deck. Needs P2TH.
        #txlist = []
        q = 0
        proposal_list = []
        tx_attr = "all_{}_txes".format(tx_type)
        for rawtx in get_marked_txes(self.provider, self.deck.derived_p2th_address(tx_type), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
            try:
                if tx_type == "donation":
                    tx = DonationTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                elif tx_type == "locking":
                    tx = LockingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                elif tx_type == "signalling":
                    tx = SignallingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)

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

                # PROVISORY/TODO: in the case of donation txes it could make sense to keep the list from pst
                self.donation_txes.update({tx.txid : tx})
                q += 1

            except (InvalidTrackedTransactionError, KeyError):
                continue
        return q

    def get_voting_txes(self, min_blockheight=None, max_blockheight=None):
        # gets ALL voting txes of a deck. Needs P2TH.
        # TODO: change this to the same model than get_tracked_txes, should be added to the Proposal State.
        # TODO: Is used in dt_utils in pacli, refactoring required.
        # uses a dict to group votes by proposal and by outcome ("positive" and "negative")
        # b'+' is the value for a positive vote, b'-' is negative, others are invalid.
        txdict = {}
        for rawtx in get_marked_txes(self.provider, self.deck.derived_p2th_address("voting"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):

            try:
                #print("raw_tx", rawtx["txid"])
                tx = VotingTransaction.from_json(tx_json=rawtx, provider=self.provider, deck=self.deck)
                #print("correct voting tx", tx.txid)
            except (KeyError, InvalidTrackedTransactionError):
                continue

            if tx.vote == b'+':
                outcome = "positive"
            elif tx.vote == b'-':
                outcome = "negative"
            else:
                continue # all other characters are invalid
            proposal_txid = tx.proposal.txid

            try:
                txdict[proposal_txid][outcome].append(tx)

            except KeyError:
                if proposal_txid in txdict: # if "outcome" still not present
                    txdict[proposal_txid].update({ outcome : [tx] })
                else: # if proposal_txid not present
                    txdict.update({ proposal_txid : { outcome : [tx] }})

        return txdict

