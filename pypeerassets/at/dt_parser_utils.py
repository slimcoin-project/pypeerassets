# This file contains minor functions for the DT parser.

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, VotingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError, DONATION_OUTPUT, DATASTR_OUTPUT
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.at.transaction_formats import *
from pypeerassets.provider import Provider
from pypeerassets.kutil import Kutil
from pypeerassets.pa_constants import param_query
from copy import deepcopy

### Transaction retrieval
### These functions retrieve all transactions of a certain type and store them in a dictionary with their basic attributes.

def get_marked_txes(provider, p2th_account, min_blockheight=None, max_blockheight=None):
    # basic function. Gets all txes sent to a P2TH address, looping through "listtransactions".
    # TODO: this needs before the address being imported into the wallet, and the account being set to its name.
    # (see import_p2th_address)

    if min_blockheight:
        min_blocktime = provider.getblock(provider.getblockhash(min_blockheight))["time"]
    if max_blockheight:
        max_blocktime = provider.getblock(provider.getblockhash(max_blockheight))["time"]
    txlist = []
    start = 0
    while True:
        newtxes = provider.listtransactions(p2th_account, 999, start)
        for tx in newtxes:
           if max_blockheight:
              if tx["blocktime"] > max_blocktime:
                  continue
           if min_blockheight:
              if tx["blocktime"] < min_blocktime:
                  continue
           
           txlist.append(provider.getrawtransaction(tx["txid"], 1))

        if len(newtxes) < 999: # lower than limit
            return txlist
        start += 999

def get_donation_txes(provider, deck, pst, min_blockheight=None, max_blockheight=None):
    # gets ALL donation txes of a deck. Needs P2TH.
    #txlist = []
    q = 0
    proposal_list = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("donation"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = DonationTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # We add the tx directly to the corresponding ProposalState.
            # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
            # When we create the first instance of the state we make a deepcopy.
            if tx.proposal_txid not in proposal_list:
                current_state = deepcopy(pst.proposal_states[tx.proposal_txid])
                current_state.all_donation_txes.append(tx)
                pst.proposal_states.update({ tx.proposal_txid : current_state })
                proposal_list.append(tx.proposal_txid)
            else:
                pst.proposal_states[tx.proposal_txid].all_donation_txes.append(tx)
            # PROVISORY/TODO: in the case of donation txes it could make sense to keep the list from pst
            pst.donation_txes.update({tx.txid : tx})
            q += 1

        except (InvalidTrackedTransactionError, KeyError):
            continue
    return q

def get_locking_txes(provider, deck, pst, min_blockheight=None, max_blockheight=None):
    # gets all locking txes of a deck. Needs P2TH.
    # txlist = []
    q = 0
    proposal_list = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("locking"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = LockingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # We add the tx directly to the corresponding ProposalState.
            # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
            # When we create the first instance of the state we make a deepcopy.
            if tx.proposal_txid not in proposal_list:
                current_state = deepcopy(pst.proposal_states[tx.proposal_txid])
                current_state.all_locking_txes.append(tx)
                pst.proposal_states.update({ tx.proposal_txid : current_state })
                proposal_list.append(tx.proposal_txid)
            else:
                pst.proposal_states[tx.proposal_txid].all_locking_txes.append(tx)
            q += 1

        except (InvalidTrackedTransactionError, KeyError):
            continue
        # txlist.append(tx) # check if this is really needed if it already is added to the ProposalState.
    #return txlist
    return q

def get_signalling_txes(provider, deck, pst, min_blockheight=None, max_blockheight=None):
    # gets all signalling txes of a deck. Needs P2TH.
    # txlist = []
    q = 0
    proposal_list = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("signalling"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = SignallingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # We add the tx directly to the corresponding ProposalState.
            # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
            # When we create the first instance of the state we make a deepcopy.
            if tx.proposal_txid not in proposal_list:
                current_state = deepcopy(pst.proposal_states[tx.proposal_txid])
                current_state.all_signalling_txes.append(tx)
                pst.proposal_states.update({ tx.proposal_txid : current_state })
                proposal_list.append(tx.proposal_txid)
            else:
                pst.proposal_states[tx.proposal_txid].all_signalling_txes.append(tx)
            q += 1
            # pst.proposal_states[tx.proposal_txid].all_signalling_txes.append(tx)
        except (InvalidTrackedTransactionError, KeyError):
            continue
        #txlist.append(tx) # check if this is really needed if it already is added to the ProposalState.
    #return txlist
    return q


def get_voting_txes(provider, deck, min_blockheight=None, max_blockheight=None):
    # gets ALL voting txes of a deck. Needs P2TH.
    # uses a dict to group votes by proposal and by outcome ("positive" and "negative")
    # b'+' is the value for a positive vote, b'-' is negative, others are invalid.
    txdict = {}
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("voting"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):

        try:
            #print("raw_tx", rawtx["txid"])
            tx = VotingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
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

def get_proposal_states(provider, deck, current_blockheight=None, all_signalling_txes=[], all_donation_txes=[], all_locking_txes=[], force_dstates=False):
    # gets ALL proposal txes of a deck and calculates the initial ProposalState. Needs P2TH.
    # if a new Proposal Transaction referencing an earlier one is found, the ProposalState is modified.
    # Modified: if provided, then donation/signalling txes are calculated
    # Modified: force_dstates option (for pacli commands) calculates all phases/rounds and DonationStates, even if no card was issued.
    statedict = {}
    used_firsttxids = []
    # print("PSTATE ALL LOCKING TX", all_locking_txes)

    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("proposal")):
        try:
            # print("rawtx:", rawtx)
            tx = ProposalTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # print("tx:", tx)
            if tx.txid not in used_firsttxids:
                state = ProposalState(first_ptx=tx, valid_ptx=tx, current_blockheight=current_blockheight, all_signalling_txes=all_signalling_txes, all_donation_txes=all_donation_txes, all_locking_txes=all_locking_txes, provider=provider)
            else:
                state = statedict[tx.txid]
                if state.first_ptx.txid == tx.first_ptx_txid:
                    state.valid_ptx = tx # TODO: This could need an additional validation step, although it is unlikely it can be used for attacks.
                else:
                    continue

        except InvalidTrackedTransactionError as e:
            print(e)
            continue

        statedict.update({ tx.txid : state })
        used_firsttxids.append(tx.txid)

    return statedict


def update_approved_proposals(pst):
    # Filters proposals which were approved in the first-round-voting.
    # TODO: To boost efficiency and avoid redundand checks, one could delete all
    # already approved proposals from the original list (which should be re-branded to "unchecked proposals")
    # Would also allow differentiate between unchecked and unapproved proposals.
    # TODO: SHould be moved as a method to ParserState.

    for pstate in pst.proposal_states.values():

        if (pstate.start_epoch != pst.epoch):
            continue

        pstate.initial_votes = get_votes(pst, pstate, pst.epoch)
        if pst.debug: print("Votes round 1 for Proposal", pstate.first_ptx.txid, ":", pstate.initial_votes)

        if pstate.initial_votes["positive"] <= pstate.initial_votes["negative"]:
            # MODIFIED: State is set to abandoned.
            pstate.state = "abandoned"
            continue

        pst.approved_proposals.update({pstate.first_ptx.txid : pstate})


def update_valid_ending_proposals(pst):
    # this function checks all proposals which end in a determinated epoch 
    # valid proposals are those who are voted in round1 and round2 with _more_ than 50% (50% is not enough).
    # MODIFIED: modified_proposals no longer parameter.
    # MODIFIED: Only checks round-2 votes.
    # TODO :Should be moved as a method to ParserState.

    ending_valid_proposals = {}
    for pstate in pst.approved_proposals.values():
        if pst.debug: print("Checking end epoch for completed proposals:", pstate.end_epoch)
        if (pstate.end_epoch != pst.epoch):
            continue
        # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
        pstate.final_votes = get_votes(pst, pstate, pst.epoch)
        if pst.debug: print("Votes round 2 for Proposal", pstate.first_ptx.txid, ":", pstate.final_votes)
        if pstate.final_votes["positive"] <= pstate.final_votes["negative"]:
            pstate.state = "abandoned"
            continue

        ending_valid_proposals.update({pstate.first_ptx.txid : pstate})

    if len(ending_valid_proposals) == 0:
        return

    pst.epochs_with_completed_proposals += 1

    # Set the Distribution Factor (number to be multiplied with the donation/slot, according to proposals and token amount)
    # Must be in a second loop as we need the complete list of valid proposals which end in this epoch.
    # Maybe this can still be optimized, with a special case if there is a single proposal in this epoch.
    # TODO: Should be probably a separate method. Would also allow to do the round checks in the same method for rd1 and 2.

    for pstate in ending_valid_proposals.values():
        if pst.current_blockheight is not None and pst.current_blockheight >= ((pst.epoch + 1) * pst.deck.epoch_length):
            if pstate.dist_factor is None:
                pstate.set_dist_factor(ending_valid_proposals.values())
                pstate.state = "completed"

    pst.valid_proposals.update(ending_valid_proposals)

## SDP
# TODO: What if there is no SDP token defined? Somebody must vote in the first round.
# An idea could be to use burn transactions in the last epoch (if it's the first epoch, then it would be simply "counting backwards") -> but this would encourage burning perhaps too much
# second idea: the deck issuer could vote for the first Proposal, or define the voters. However, this would make the token have a centralized element.
# "all proposals are voted" or "voting by the donors" are not possible as they have a risk of cheating.

def get_sdp_weight(epochs_from_start: int, sdp_periods: int) -> Decimal:
    # Weight calculation for SDP token holders
    # This function rounds percentages, to avoid problems with period lengths like 3.
    # (e.g. if there are 3 SDP epochs, last epoch will have weight 0.33)
    # IMPROVEMENT: Maybe it would make sense if this gives an int value which later is divided into 100,
    # because anyway there must be some rounding being done.
    return (Decimal((sdp_periods - epochs_from_start) * 100) // sdp_periods) / 100

### Voting

def update_voters(voters={}, new_cards=[], weight=1, dec_diff=0, debug=False):

    # It is only be applied to new_cards if they're SDP cards (as these are the SDP cards added).
    # voter dict:
    # key: sender (address)
    # value: combined value of card_transfers (can be negative).
    # The dec_diff value is the difference between number_of_decimals of main deck/sdp deck.
    # dec_diff isn't applied to old voters, thus it cannot be merged with "weight".

    # TODO: The dec_adjustment calculation will throw Type problems if the SDP token has more decimals as the main token.
    # Perhaps use it as a decimal, and then convert all values to int again (check the precision!)

    #if debug: print("Voters", voters, "\nWeight:", weight)
    dec_adjustment = 10 ** dec_diff
    # dec_adjustment = 1 # test

    # 1. Update cards of old SDP voters by weight.
    if weight != 1:
        for voter in voters:
           # MODIFIED: Adjustment to get rounding to the precision of the voting token.
           old_amount = Decimal(voters[voter]) / dec_adjustment
           new_amount = int(old_amount * weight) * dec_adjustment
           voters.update({voter : new_amount})
           # old one:
           #old_amount = voters[voter]
           #voters.update({ voter : int(old_amount * weight) })
           if debug: print("Updating SDP balance:", old_amount * 10 ** dec_diff, "to:", voters[voter], "- weight:", weight)

    # 2. Add votes of new cards
    for card in new_cards:
        # if debug: print("Card data:", card.sender, card.receiver, card.amount, card.type)

        if card.type != "CardBurn":

            for receiver in card.receiver:
                rec_position = card.receiver.index(receiver)
                rec_amount = int(card.amount[rec_position] * weight) * dec_adjustment

                if receiver not in voters:
                    if debug: print("New voter:", receiver, "with amount:", rec_amount)
                    voters.update({receiver : rec_amount })
                else:
                    old_amount = voters[receiver]
                    if debug: print("Voter:", receiver, "with old_amount:", old_amount, "updated to new amount:", old_amount + rec_amount)
                    
                    voters.update({receiver : old_amount + rec_amount})

        # if cardissue, we only add balances to receivers, nothing is deducted.
        # Donors have to send the CardIssue to themselves if they want their coins.
        if card.type in ("CardTransfer", "CardBurn"):
            rest = -int(sum(card.amount)) # MODIFIED: weight here does not apply!
            if card.sender not in voters:
                if debug: print("Card sender not in voters. Resting the rest:", rest)
                voters.update({card.sender : rest * dec_adjustment})
            else:
                old_amount = voters[card.sender]
                if debug: print("Card sender updated from:", old_amount, "to:", old_amount + rest * dec_adjustment)
                voters.update({card.sender : old_amount + rest * dec_adjustment})

    return voters

def get_votes(pst, proposal, epoch, formatted_result=False):
    # returns a dictionary with two keys: "positive" and "negative",
    # containing the amounts of the tokens with whom an address was voted.
    # NOTE: The balances are valid for the epoch of the ParserState. So this cannot be called
    #       for votes in other epochs.
    # NOTE 2: In this protocol the last vote counts (this is why the vtxs list is reversed).
    #       You can always change you vote.
    # TODO: This is still without the "first vote can also be valid for second round" system.
    # Formatted_result returns the "decimal" value of the votes, i.e. the number of "tokens"
    # which voted for the proposal, which depends on the "number_of_decimals" value.
    # TODO: Trash the epoch value, it should always be taken from pst! (if not, then there is a structural problem!)
    # TODO: ProposalState should have attributes to show every single vote and their balances (at least optional, for the pacli commands).

    votes = {}
    voters = [] # to filter out duplicates.
    debug = pst.debug

    if debug: print("Enabled Voters:", pst.enabled_voters)
    try:
        vtxes_proposal = pst.voting_txes[proposal.first_ptx.txid]
    except KeyError: # gets thrown if the proposal was not added to pst.voting_txes, i.e. when no votes were found.
        return {"positive" : 0, "negative" : 0}

    voting_txes = []
    for outcome in ("positive", "negative"):
        if outcome in vtxes_proposal:
            voting_txes += vtxes_proposal.get(outcome)

    sorted_vtxes = sorted(voting_txes, key=lambda tx: tx.blockheight, reverse=True)
    
    votes = { "negative" : 0, "positive" : 0 }

    for v in sorted_vtxes: # reversed for the "last vote counts" rule.
        if debug: print("Vote: Epoch", v.epoch, "txid:", v.txid, "sender:", v.sender, "outcome:", v.vote, "height", v.blockheight)
        if (v.epoch == epoch) and (v.sender not in voters):
            try:
                if debug: print("Vote is valid.")
                voter_balance = pst.enabled_voters[v.sender] # voting token balance at start of epoch
                if debug: print("Voter balance", voter_balance)
                vote_outcome = "positive" if v.vote == b'+' else "negative"
                votes[vote_outcome] += voter_balance
                if debug: print("Balance of outcome", vote_outcome, "increased by", voter_balance)
                voters.append(v.sender)

            except KeyError: # will always be thrown if a voter is not enabled in the "current" epoch.
                if debug: print("Voter has no balance in the current epoch.")
                continue

        elif v.epoch < epoch: # due to it being sorted we can cut off all txes before the relevant epoch.
            break

    if formatted_result:
        for outcome in ("positive", "negative"):
            balance = Decimal(votes[outcome]) / 10**pst.deck.number_of_decimals
            # modified: base is number_of_decimals of main deck. old version:
            # balance = Decimal(votes[outcome]) / 10**pst.sdp_deck.number_of_decimals

            votes.update({outcome : balance})
 
    return votes

### Other utils

def deck_from_tx(txid: str, provider: Provider, deck_version: int=1, prod: bool=True):
    '''Wrapper for deck_parser, gets the deck from the TXID.'''
    from pypeerassets.pautils import deck_parser

    params = param_query(provider.network)
    p2th = params.P2TH_addr
    raw_tx = provider.getrawtransaction(txid, 1)
    # vout = raw_tx["vout"][0]["scriptPubKey"].get("addresses")[0] ???
    return deck_parser((provider, raw_tx, deck_version, p2th), prod)
