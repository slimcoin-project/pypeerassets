""" Basic parser for DT cards with the major validation steps.
It loops through the cards by epoch, instead by card. This allows to update the enabled voters in each epoch,
and so calculate the valid proposals which were selected from the next epoch.
Minor functions are in dt_parser_utils. """

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, VotingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.extended_utils import get_issuance_bundle
import pypeerassets.at.constants as c
import pypeerassets as pa
import pypeerassets.at.dt_parser_utils as dpu
from copy import deepcopy

class ParserState(object):
    """A ParserState contains the current state of all important variables for a single dPoD (DT) deck,
       while the card parser is running.
       A sub_state is a dict to allow to create a ParserState in a pre-processed state.
       Currently not used but useful for further updates."""

    def __init__(self, deck: object, initial_cards: list, provider: object, epoch: int=None, start_epoch: int=None, end_epoch: int=None,  current_blockheight: int=None, debug: bool=False, debug_voting: bool=False, debug_donations: bool=False, epochs_with_completed_proposals: int=0, **sub_state):
        """Initializing is done in two parts: main attributes and sub-state attributes (keyword arguments)."""

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
        # MODIF: added sdp_voters and dpod_voters, need to be segregated.
        dict_items = ("proposal_states", "approved_proposals", "valid_proposals", "donation_txes", "enabled_voters", "sdp_voters", "dpod_voters")
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
        """Bundles all on-chain transaction retrievals (SDP cards and TrackedTransactions)."""

        # Initial balance of SDP cards
        if self.sdp_deck != None:
            self.sdp_cards = self.get_sdp_cards()
        else:
            self.sdp_cards = None

        if self.debug: print("PARSER: Get proposal states ...", )
        self.proposal_states = dpu.get_proposal_states(self.provider, self.deck, self.current_blockheight, debug=self.debug)
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
        """Allows to set all donation states even if no card has been issued."""

        for p in self.proposal_states.values():
            if self.debug_donations: print("PARSER: Setting donation states for Proposal:", p.id)

            # We must ensure process_donation_states is only called once per phase, otherwise
            # Locking/DonationTransactions will not be added (because of the 1 state per donor address restriction)
            # "processed" variable prevents this with a simple check.
            phase = 1 if self.epoch <= p.end_epoch else 0
            if not p.processed[phase]:
                p.set_donation_states(self.current_blockheight, debug=self.debug_donations)

    def get_sdp_cards(self):
        """Retrieves the SDP cards."""

        from pypeerassets.__main__ import find_all_valid_cards

        if self.debug_voting: print("VOTING: Searching for SDP Token Cards ...")
        all_sdp_cards = list(find_all_valid_cards(self.provider, self.sdp_deck))
        valid_sdp_cards = self.remove_invalid_cards(all_sdp_cards)
        return valid_sdp_cards

    @staticmethod
    def remove_invalid_cards(cards):
        """Filters out all invalid cards. It uses the DeckState from PeerAssets with a slight modification."""
        # TODO: could perhaps better fit in the dt_parser_utils module. Is not uses in other modules.

        from pypeerassets.protocol import DeckState

        state = DeckState(cards)
        return state.valid_cards

    def get_sdp_epoch_cards(self):
        """Processes all valid transfers from self.sdp_cards of the SDP token up to the last block before the current epoch."""
        # NOTE: If this is called in the start epoch, then all SDP cards up to the last block before the start epoch are processed.
        # Otherwise only the last epoch before the current epoch start is retrieved.
        # TODO: To improve code maintainability this could be changed in the following way:
        # - it gets called from epoch_postprocess instead of epoch_init
        # - this function is changed so the *current* epoch is checked, not the last epoch.
        # re-check this!

        next_epoch_start = self.epoch * self.deck.epoch_length # balance at the start of the epoch.

        if self.epoch == self.start_epoch:
            if self.debug_voting: print("VOTING: Retrieving old SDP cards ...")
            first_epoch_block = 0
        else:
            first_epoch_block = (self.epoch - 1) * self.deck.epoch_length # balance at the start of the epoch.

        # NOTE: changed, as the next_epoch_start block is not more valid for this epoch, see below.
        if self.debug_voting: print("VOTING: Last block for current epoch {}: {}".format(self.epoch, next_epoch_start - 1))
        if self.debug_voting: print("VOTING: SDP Card blocks:", [card.blocknum for card in self.sdp_cards])

        cards = [card for card in self.sdp_cards if (first_epoch_block <= card.blocknum < next_epoch_start)]

        return cards

    def update_approved_proposals(self):
        """Filters proposals which were approved in the first voting phase."""
        # TODO: To boost efficiency and avoid redundant checks, one could delete all
        # already approved proposals from the original list (which should be renamed to "unchecked proposals")
        # Would also allow differentiate between unchecked and unapproved proposals.

        for pstate in self.proposal_states.values():

            if (pstate.start_epoch != self.epoch):
                continue

            pstate.process_votes(self.enabled_voters, phase=0, debug=self.debug_voting)

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
        """Checks all proposals which end in a determinated epoch.
         Valid proposals are those who are voted in both voting phases with _more_ than 50% (50% is not enough).
         Only checks round-2 votes."""

        ending_valid_proposals = {}
        for pstate in self.approved_proposals.values():

            if (pstate.end_epoch != self.epoch):
                continue
            # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
            pstate.process_votes(self.enabled_voters, phase=1, debug=self.debug_voting)
            if self.debug_voting: print("VOTING: Votes round 2 for Proposal", pstate.id, ":", pstate.final_votes)
            if pstate.final_votes["positive"] <= pstate.final_votes["negative"]:
                pstate.state = "abandoned"
                continue
            ending_valid_proposals.update({pstate.first_ptx.txid : pstate})

        if self.debug_voting: print("PARSER: Completed proposals in epoch {}: {}".format(self.epoch, ending_valid_proposals.keys()))
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

        # SDP balances are updated according to reduction formula by SDP period
        # this was previously in the wrong place.

        sdp_weight = dpu.get_sdp_weight(self.epochs_with_completed_proposals, self.deck.sdp_periods)
        dpu.update_sdp_weight(voters=self.sdp_voters, weight=sdp_weight, dec_diff=self.sdp_decimal_diff, debug=self.debug_voting)

    def get_tracked_txes(self, tx_type, min_blockheight=None, max_blockheight=None):
        """Retrieves TrackedTransactions (except votes and proposals) for a deck from the blockchain
           and adds them to the corresponding ProposalState."""

        proposal_list = []
        tx_attr = "all_{}_txes".format(tx_type)
        # p2th_account = self.deck.derived_p2th_address(tx_type) # OLD behaviour
        p2th_account = self.deck.id + tx_type.upper()
        txes = dpu.get_marked_txes(self.provider, p2th_account, min_blockheight=min_blockheight, max_blockheight=max_blockheight)
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

    def validate_proposer_issuance(self, dtx_id, card_units, card_sender, card_blocknum):
        """Validation method for proposers. The dtx_id here is the ProposalTransaction's TXID."""

        debug = self.debug_donations
        proposal_state = self.valid_proposals[dtx_id] # checked just before the call, so no "try/except" necessary.

        if debug: print("PARSER: Checking Proposer issuance based on proposal", proposal_state.id)
        # 1. Check if the card issuer is identical to the Proposer.
        if card_sender not in proposal_state.valid_ptx.input_addresses:
            if debug: print("PARSER: Proposer issuance failed: Incorrect card issuer.")
            return False

        if len(proposal_state.donation_states) == 0:
            proposal_state.set_donation_states(self.current_blockheight)

        # 2. Check correct amount
        if card_units != proposal_state.proposer_reward:
            if debug: print("PARSER: Proposer issuance failed: Incorrect amount.")
            return False

        return True

    def validate_donation_issuance(self, dtx_id, card_units, card_sender):
        """Main validation function for donations. Checks for each issuance if the donation was correct.
        The donation transaction ID is provided (by the issue transaction)
        and it is checked if it corresponds to a real donation."""

        debug = self.debug_donations

        if debug: print("PARSER: Checking CardIssue based on donation tx:", dtx_id)

        # check A: do donation transaction and proposal exist?
        if debug: print("PARSER: Valid proposals:", self.valid_proposals)

        # Retrieve DonationTransaction object.
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

        # We only create donation states for Proposals where a card was issued.
        if len(proposal_state.donation_states) == 0:
            if debug: print("PARSER: Creating donation states ...")
            proposal_state.set_donation_states(self.current_blockheight, debug=self.debug_donations)

        if debug: print("PARSER: Number of donation txes:", len([tx for r in proposal_state.donation_txes for tx in r ]))

        # check B: Does the txid correspond to a valid DonationTransaction?
        # We go through the DonationStates per round and search for the dtx_id.
        # When we find it, we get the DonationState for the card issuance.

        for rd_states in proposal_state.donation_states:
            for ds in rd_states.values():
                try:
                    if ds.donation_tx.txid == dtx.txid:
                        break
                except AttributeError:
                    continue
            else:
                continue
            break

        else:
            if debug: print("PARSER: Donation issuance failed: No matching donation state found.")
            return False

        # Check C: The card issuance transaction was signed really by the donor?
        if card_sender != ds.donor_address:
            if debug: print("PARSER: Donation issuance failed: Card sender {} not corresponding to donor address {}".format(card_sender, ds.donor_address))
            return False

        if debug: print("PARSER: Initial slot:", ds.slot, "Effective slot:", ds.effective_slot)
        if debug: print("PARSER: Donation amount:", ds.donated_amount)
        if debug: print("PARSER: Card amount:", card_units)
        if debug: print("PARSER: Calculated reward:", ds.reward)
        if debug: print("PARSER: Distribution Factor:", proposal_state.dist_factor)


        # Check D: Was the issued amount correct?
        if card_units != ds.reward:
            if debug: print("PARSER: Donation issuance failed: Incorrect issued token amount, different from the assigned slot.")
            return False
        else:
            ds.state = "claimed"
            return True

    def check_card(self, card, issued_amount=None):
        """Checks a CardIssue for validity. CardTransfers are always valid (they will be later processed by DeckState)."""

        # MODIF: issued_amount is only used for CardIssues as we need to know how much was issued in the bundle.
        # CONVENTION: voters' weight is the balance at the start block of current epoch

        debug = self.debug_donations

        if card.type == "CardIssue":
            if debug: print("PARSER: Checking validity of CardIssue", card.txid, "based on txid:", card.donation_txid)

            # First step: Look for a matching DonationTransaction.
            dtx_id = card.donation_txid

            # check 1: filter out duplicates (less expensive, so done first)
            if (card.sender, dtx_id) in self.used_issuance_tuples:
                if debug: print("PARSER: Ignoring CardIssue: Duplicate or already processed part of CardBundle.")
                return False

            # Check if it is a proposer or a donation issuance.
            # Proposers provide the ref_txid of their proposal transaction.
            # If this TX is in proposal_txes and they are the sender of the card and fulfill all requirements,
            # then the token is granted to them at their proposal address.

            if (dtx_id in self.valid_proposals) and self.validate_proposer_issuance(dtx_id, issued_amount, card.sender, card.blocknum):
                if debug: print("PARSER: DT CardIssue (Proposer):", card.txid)

            elif self.validate_donation_issuance(dtx_id, issued_amount, card.sender):
                if debug: print("PARSER: DT CardIssue (Donation):", card.txid)

            else:
                if debug: print("PARSER: Ignoring CardIssue: Invalid data.")
                return False

            self.used_issuance_tuples.append((card.sender, dtx_id))
            return True

        else:

            if debug: print("PARSER: DT CardTransfer:", card.txid)
            return True

    def epoch_init(self):
        """Called when the card loop enters a new epoch.
           Calculates SDP voter balances, then updates states of approved and ending proposals."""

        debug = self.debug_voting
        epoch_firstblock, epoch_lastblock = self.epoch * self.deck.epoch_length, (self.epoch + 1) * self.deck.epoch_length - 1
        if debug: print("PARSER: Checking epoch:", self.epoch, ", from block", epoch_firstblock, "to", epoch_lastblock)

        if self.deck.sdp_periods: # should give true if 0 or None

            sdp_epochs_remaining = self.deck.sdp_periods - self.epochs_with_completed_proposals
            if debug: print("VOTING: Epochs with completed proposals:", self.epochs_with_completed_proposals)
            if debug: print("VOTING: SDP periods remaining:", sdp_epochs_remaining)

            if sdp_epochs_remaining <= self.deck.sdp_periods:

                # We set apart all CardTransfers of SDP voters before the epoch start
                sdp_epoch_cards = self.get_sdp_epoch_cards()

                if len(sdp_epoch_cards) > 0:
                    updated_sdp_voters = dpu.update_voters(sdp=True, voters=self.sdp_voters, new_cards=sdp_epoch_cards, debug=self.debug_voting, dec_diff=self.sdp_decimal_diff)
                    self.sdp_voters.update(updated_sdp_voters)
                    self.update_enabled_voters()
                    if self.debug_voting: print("VOTING: SDP Voters updated to:", self.sdp_voters)


        # As card issues can occur any time after the proposal has been voted
        # we always need to process all valid proposals voted up to this epoch.

        if debug: print("VOTING: Get ending proposals ...")

        self.update_approved_proposals()
        if debug: print("VOTING: Approved proposals after epoch", self.epoch, list(self.approved_proposals.keys()))

        self.update_valid_ending_proposals()
        if debug: print("VOTING: Valid ending proposals after epoch:", self.epoch, list(self.valid_proposals.keys()))


    def update_enabled_voters(self):
        for voter in self.enabled_voters:

            sdp_balance = self.sdp_voters[voter] if voter in self.sdp_voters else Decimal("0")
            dpod_balance = self.dpod_voters[voter] if voter in self.dpod_voters else Decimal("0")
            if self.debug_voting:
                orig_balance = self.enabled_voters[voter] if voter in self.enabled_voters else Decimal("0")
                print("VOTING: Enabled voter {} updated: Original balance: {} SDP: {} dPoD: {}".format(voter, orig_balance, sdp_balance, dpod_balance))
            self.enabled_voters.update({voter : sdp_balance + dpod_balance})

        for dpod_voter in self.dpod_voters:
            if dpod_voter not in self.enabled_voters:
                dpod_balance = self.dpod_voters[dpod_voter]
                self.enabled_voters.update({dpod_voter : dpod_balance})
                if self.debug_voting:
                    print("VOTING: New enabled dPoD voter: {} with balance {}.".format(dpod_voter, dpod_balance))

        for sdp_voter in self.sdp_voters:
            if sdp_voter not in self.enabled_voters:
                sdp_balance = self.sdp_voters[sdp_voter]
                self.enabled_voters.update({sdp_voter : sdp_balance})
                if self.debug_voting:
                    print("VOTING: New enabled SDP voter: {} with balance {}.".format(sdp_voter, sdp_balance))


    def epoch_postprocess(self, valid_epoch_cards):
        """Postprocesses epochs with cards."""
        # if debug: print("Valid cards found in this epoch:", len(valid_epoch_cards))

        self.dpod_voters.update(dpu.update_voters(voters=self.dpod_voters, new_cards=valid_epoch_cards, debug=self.debug_voting))

        # NEW method: updating of SDP voters in enabled_voters requires checking those in both categories.
        self.update_enabled_voters()

        self.valid_cards += valid_epoch_cards


    def process_cardless_epochs(self, start, end):
        """Process all epochs without cards between start and end."""

        for epoch in range(start, end + 1):
            self.epoch = epoch
            self.epoch_init()
            # the postprocess step can be skipped, as there are no cards.


