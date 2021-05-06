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

    def __init__(self, deck, initial_cards, provider, proposal_states={}, approved_proposals={}, valid_proposals={}, signalling_txes=[], locking_txes=[], donation_txes={}, voting_txes=[], epoch=None, start_epoch=None, end_epoch=None, used_issuance_tuples=[], valid_cards=[], enabled_voters={}, sdp_cards=[], sdp_deck_obj=None, current_blockheight=None, epochs_with_completed_proposals=0, debug=False):

        self.deck = deck
        self.initial_cards = initial_cards
        self.provider = provider
        self.current_blockheight = current_blockheight

        self.valid_cards = valid_cards
        self.proposal_states = proposal_states
        self.approved_proposals = approved_proposals # approved by round 1 votes
        self.valid_proposals = valid_proposals # successfully completed: approved by round 1 + 2 votes 
        self.signalling_txes = signalling_txes # TODO: PROBABLY obsolete!
        self.locking_txes = locking_txes # TODO: probably obsolete!
        self.donation_txes = donation_txes # MODIFIED as a dict!
        self.voting_txes = voting_txes # this is a dict, not list.
        self.epochs_with_completed_proposals = epochs_with_completed_proposals

        # enabled_voters variable is calculated once per epoch, taking into account card issuances and card transfers.
        # enabled_voters are all voters with valid balances, and their balance.
        self.enabled_voters = enabled_voters
        # SDP voters/balances are stored as CardTransfers, so they can be easily retrieved with PeerAsset standard methods.
        if self.deck.sdp_deck:
            self.sdp_deck_obj = deck_from_tx(self.deck.sdp_deck, self.provider)
        else:
            self.sdp_deck_obj = sdp_deck_obj
        self.sdp_cards = sdp_cards

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
        if self.sdp_deck_obj != None:
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
        # self.donation_txes = get_donation_txes(self.provider, self.deck, self)
        q = get_donation_txes(self.provider, self.deck, self)
        if self.debug: print(q, "found.")

        if self.debug: print("Get locking txes ...", )
        # self.locking_txes = get_locking_txes(self.provider, self.deck, self)
        q = get_locking_txes(self.provider, self.deck, self)
        if self.debug: print(q, "found.")

        if self.debug: print("Get signalling txes ...", )
        # self.signalling_txes = get_signalling_txes(self.provider, self.deck, self)
        q = get_signalling_txes(self.provider, self.deck, self)
        if self.debug: print(q, "found.")

        if self.debug: print("Get voting txes ...", )
        self.voting_txes = get_voting_txes(self.provider, self.deck)
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
        return list(find_all_valid_cards(self.provider, self.sdp_deck_obj))
