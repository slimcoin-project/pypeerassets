# This file contains minor functions for the DT parser.

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, VotingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError, DONATION_OUTPUT, DATASTR_OUTPUT
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.at.transaction_formats import *
from pypeerassets.provider import Provider
from pypeerassets.kutil import Kutil
from pypeerassets.pa_constants import param_query
from pypeerassets.pautils import deck_parser

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
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("donation"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = DonationTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # We add the tx directly to the corresponding ProposalState.
            # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
            pst.proposal_states[tx.proposal_txid].all_donation_txes.append(tx)
        except (InvalidTrackedTransactionError, KeyError):
            continue
        txlist.append(tx)
    return txlist


def get_locking_txes(provider, deck, pst, min_blockheight=None, max_blockheight=None):
    # gets all locking txes of a deck. Needs P2TH.
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("locking"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = LockingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # We add the tx directly to the corresponding ProposalState.
            # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
            pst.proposal_states[tx.proposal_txid].all_locking_txes.append(tx)

        except (InvalidTrackedTransactionError, KeyError):
            continue
        txlist.append(tx) # check if this is really needed if it already is added to the ProposalState.
    return txlist

def get_signalling_txes(provider, deck, pst, min_blockheight=None, max_blockheight=None):
    # gets all signalling txes of a deck. Needs P2TH.
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("signalling"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = SignallingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            # We add the tx directly to the corresponding ProposalState.
            # If the ProposalState does not exist, KeyError is thrown and the tx is ignored.
            pst.proposal_states[tx.proposal_txid].all_signalling_txes.append(tx)
        except (InvalidTrackedTransactionError, KeyError):
            continue
        txlist.append(tx) # check if this is really needed if it already is added to the ProposalState.
    return txlist


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
            continue # invalid
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

        votes_round1 = get_votes(pst, pstate, pst.epoch)
        if pst.debug: print("Votes round 1 for Proposal", pstate.first_ptx.txid, ":", votes_round1)

        if votes_round1["positive"] <= votes_round1["negative"]:
            continue

        pst.approved_proposals.update({pstate.first_ptx.txid : pstate})


def update_valid_ending_proposals(pst):
    # this function checks all proposals which end in a determinated epoch 
    # valid proposals are those who are voted in round1 and round2 with _more_ than 50% (50% is not enough).
    # MODIFIED: modified_proposals no longer parameter.
    # MODIFIED: Only checks round-2 votes.
    # TODO :Should be moved as a method to ParserState.

    for pstate in pst.approved_proposals.values():
        if pst.debug: print("Checking end epoch for completed proposals:", pstate.end_epoch)
        if (pstate.end_epoch != pst.epoch):
            continue
        # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
        votes_round2 = get_votes(pst, pstate, pst.epoch)
        if pst.debug: print("Votes round 2 for Proposal", pstate.first_ptx.txid, ":", votes_round2)
        if votes_round2["positive"] <= votes_round2["negative"]:
            continue

        pst.valid_proposals.update({pstate.first_ptx.txid : pstate})
    else:
        return

    pst.epochs_with_completed_proposals += 1

    # Set the Distribution Factor (number to be multiplied with the donation/slot, according to proposals and token amount)
    # Must be in a second loop as we need the complete list of valid proposals which end in this epoch.
    # Maybe this can still be optimized, with a special case if there is a single proposal in this epoch.
    # TODO: SHould be probably a separate method. Would also allow to do the round checks in the same method for rd1 and 2.

    for pstate in pst.valid_proposals.values():
        if not pstate.dist_factor:
            pstate.set_dist_factor(pst.valid_proposals.values())


def get_valid_ending_proposals_old(pst, deck):
    # this function checks all proposals which end in a determinated epoch 
    # valid proposals are those who are voted in round1 and round2 with _more_ than 50% (50% is not enough).
    # MODIFIED: modified_proposals no longer parameter.
    # TODO: Round 1 calculation does not work properly. We need to track the votes at this epoch. This will probably require an additional attribute for ParserState, e.g. voting_state, updated in each round.

    proposal_states, epoch, epoch_length, enabled_voters = pst.proposal_states, pst.epoch, deck.epoch_length, pst.enabled_voters

    valid_proposals = {}

    for pstate in proposal_states.values():
        if pst.debug: print("Checking end epoch for completed proposals:", pstate.end_epoch)
        if (pstate.end_epoch != epoch):
            continue
        # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
        votes_round2 = get_votes(pst, pstate, epoch)
        if pst.debug: print("Votes round 2 for Proposal", pstate.first_ptx.txid, ":", votes_round2)
        if votes_round2["positive"] <= votes_round2["negative"]:
            continue
        votes_round1 = get_votes(pst, pstate, pstate.start_epoch)
        if pst.debug: print("Votes round 1 for Proposal", pstate.first_ptx.txid, ":", votes_round1)
        if votes_round1["positive"] <= votes_round1["negative"]:
            continue  
        valid_proposals.update({pstate.first_ptx.txid : pstate})

    # Set the Distribution Factor (number to be multiplied with the donation/slot, according to proposals and token amount)
    # Must be in a second loop as we need the complete list of valid proposals which end in this epoch.
    # Maybe this can still be optimized, with a special case if there is a single proposal in this epoch.

    for pstate in valid_proposals.values():
        if not pstate.dist_factor:
            pstate.set_dist_factor(valid_proposals.values())

    return valid_proposals

## SDP
# TODO: What if there is no SDP token defined? Somebody must vote in the first round.
# An idea could be to use burn transactions in the last epoch (if it's the first epoch, then it would be simply "counting backwards") -> but this would encourage burning perhaps too much
# second idea: the deck issuer could vote for the first Proposal, or define the voters. However, this would make the token have a centralized element.
# "all proposals are voted" or "voting by the donors" are not possible as they have a risk of cheating.

def get_sdp_balances(pst):

    limit_blockheight = pst.epoch * pst.deck.epoch_length # balance at the start of the epoch.
    if pst.debug: print("Blocklimit for this epoch:", limit_blockheight, "Epoch number:", pst.epoch)
    if pst.debug: print("Card blocks:", [card.blocknum for card in pst.sdp_cards])

    # TODO: define if the limit is the last block of epoch before, or first block of current epoch!
    cards = [ card for card in pst.sdp_cards if card.blocknum <= limit_blockheight ]

    return cards

def get_sdp_weight(epochs_from_start: int, sdp_periods: int) -> Decimal:
    # Weight calculation for SDP token holders
    # This function rounds percentages, to avoid problems with period lengths like 3.
    # (e.g. if there are 3 SDP epochs, last epoch will have weight 0.33)
    # IMPROVEMENT: Maybe it would make sense if this gives an int value which later is divided into 100,
    # because anyway there must be some rounding being done.
    return (Decimal((sdp_periods - epochs_from_start) * 100) // sdp_periods) / 100

### Voting

def update_voters(voters={}, new_cards=[], weight=1, debug=False):
    # voter dict:
    # key: sender (address)
    # value: combined value of card_transfers (can be negative).
    # MODIFIED: added weight, this is for SDP voters. Added CardBurn.

    if debug: print("Voters", voters, "\nWeight:", weight)
    if weight != 1:
        for voter in voters:
           old_amount = voters[voter]
           voters.update({ voter : int(old_amount * weight) })
           if debug: print("Updating SDP balance:", old_amount, "to:", voters[voter])

    for card in new_cards:
        if debug: print("Card data:", card.sender, card.receiver, card.amount, card.type)

        if card.type != "CardBurn":

            for receiver in card.receiver:
                rec_position = card.receiver.index(receiver)
                rec_amount = int(card.amount[rec_position] * weight)

                if receiver not in voters:
                    if debug: print("New voter:", receiver, "with amount:", rec_amount)
                    voters.update({receiver : rec_amount})
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
                voters.update({card.sender : rest})
            else:
                old_amount = voters[card.sender]
                if debug: print("Card sender updated from:", old_amount, "to:", old_amount + rest)
                voters.update({card.sender : old_amount + rest})

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
    # TODO: WE probably need a parameter of proposals showing always the votes got in a particular epoch.

    votes = {}
    voters = [] # to filter out duplicates.

    if pst.debug: print("Enabled Voters:", pst.enabled_voters)
    try:
        voting_txes = pst.voting_txes[proposal.first_ptx.txid]["positive"] + pst.voting_txes[proposal.first_ptx.txid]["negative"]
    except KeyError: # gets thrown if the proposal was not added to pst.voting_txes, i.e. when no votes were found.
        return {"positive" : 0, "negative" : 0}
    sorted_vtxes = sorted(voting_txes, key=lambda tx: tx.blockheight, reverse=True) # newlist = sorted(ut, key=lambda x: x.count, reverse=True) # this is a workaround.
    
    votes = { "negative" : 0, "positive" : 0 }

    for v in sorted_vtxes: # reversed for the "last vote counts" rule.
        if pst.debug: print("Vote: Epoch", v.epoch, "txid:", v.txid, "sender:", v.sender, "outcome:", v.vote, "height", v.blockheight)
        if (v.epoch == epoch) and (v.sender not in voters):
            try:
                if pst.debug: print("Vote is valid.")
                voter_balance = pst.enabled_voters[v.sender] # voting token balance at start of epoch
                if pst.debug: print("Voter balance", voter_balance)
                vote_outcome = "positive" if v.vote == b'+' else "negative"
                votes[vote_outcome] += voter_balance
                if pst.debug: print("Balance of outcome", vote_outcome, "increased by", voter_balance)
                voters.append(v.sender)

            except KeyError: # will always be thrown if a voter is not enabled in the "current" epoch.
                if pst.debug: print("Voter has no balance in the current epoch.")
                continue

    if formatted_result:
        for outcome in ("positive", "negative"):
            dec_balance = Decimal(votes[outcome])
            balance = dec_balance / 10**pst.sdp_deck_obj.number_of_decimals

            votes.update({outcome : balance})
 
    return votes

def deck_from_tx(txid: str, provider: Provider, deck_version: int=1, prod: bool=True):
    '''Wrapper for deck_parser, gets the deck from the TXID.'''

    params = param_query(provider.network)
    p2th = params.P2TH_addr
    raw_tx = provider.getrawtransaction(txid, 1)
    vout = raw_tx["vout"][0]["scriptPubKey"].get("addresses")[0]
    return deck_parser((provider, raw_tx, deck_version, p2th), prod)
