# This file contains minor functions for the DT parser.

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, DonationTransaction, LockingTransaction, VotingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError, DONATION_OUTPUT, DATASTR_OUTPUT
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.provider import Provider
from pypeerassets.kutil import Kutil
from pypeerassets.at.transaction_formats import *

# modified: constants went to at_transaction_formats

### Address and P2TH tools

def import_p2th_address(provider: Provider, p2th_address: str) -> None:
    # this checks if a P2TH address is already imported. If not, import it (only rpcnode).
    p2th_account = provider.getaccount(p2th_address)

    if (type(p2th_account) == dict) and (p2th_account.get("code") == -5):
        raise ValueError("Invalid address.")

    if (p2th_account is None) or (p2th_account != p2th_address):
        provider.importaddress(p2th_address)
        provider.setaccount(p2th_address, p2th_address) # address is also the account name.

def deck_p2th_from_id(network: str, deck_id: str) -> str:
    # helper function giving the p2th.
    return Kutil(network=network,
                         privkey=bytearray.fromhex(deck_id)).address

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
        txlist.append(tx) # TODO: do we still need this complete list? It is probably better to keep it for DonationTransactions, to be able to create the DonationTX for the parser without additional blockchain lookup. For signalling/locking probably we don't need it.
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

def get_proposal_txes(provider, deck, min_blockheight=None, max_blockheight=None):
    # gets ALL proposal txes of a deck. Needs P2TH.
    # TODO: I think this was obsolete, as it's replaced by get_proposal_states. Not included in test suite.
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("proposal"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):
        try:
            tx = ProposalTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
        except InvalidTrackedTransactionError:
            continue
        txlist.append(tx)
    return txlist

def get_voting_txes(provider, deck, min_blockheight=None, max_blockheight=None):
    # gets ALL proposal txes of a deck. Needs P2TH.
    # uses a dict to group votes by proposal and by outcome ("positive" and "negative")
    # b'+' is the value for a positive vote, b'-' is negative, others are invalid.
    txdict = {}
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("voting"), min_blockheight=min_blockheight, max_blockheight=max_blockheight):

        try:
            tx = VotingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
        except InvalidTrackedTransactionError:
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

def get_proposal_states(provider, deck, current_blockheight=None, all_signalling_txes=None, all_donation_txes=None, all_locking_txes=None):
    # gets ALL proposal txes of a deck and calculates the initial ProposalState. Needs P2TH.
    # if a new Proposal Transaction referencing an earlier one is found, the ProposalState is modified.
    # Modified: if provided, then donation/signalling txes are calculated
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
                    state.valid_ptx = tx
                else:
                    continue

        except InvalidTrackedTransactionError as e:
            print(e)
            continue

        statedict.update({ tx.txid : state })
        used_firsttxids.append(tx.txid)

    return statedict


def get_valid_ending_proposals(pst, deck):
    # this function checks all proposals which end in a determinated epoch 
    # valid proposals are those who are voted in round1 and round2 with _more_ than 50% (50% is not enough).
    # MODIFIED: modified_proposals no longer parameter.

    proposal_states, epoch, epoch_length, enabled_voters = pst.proposal_states, pst.epoch, deck.epoch_length, pst.enabled_voters

    valid_proposals = {}

    for pstate in proposal_states.values():
        print("End epoch", pstate.end_epoch)
        if (pstate.end_epoch != epoch):
            continue
        # donation address should not be possible to change (otherwise it's a headache for donors), so we use first ptx.
        votes_round2 = get_votes(pst, pstate, epoch)
        print("Votes:", votes_round2)
        if votes_round2["positive"] <= votes_round2["negative"]:
            continue
        votes_round1 = get_votes(pst, pstate, pstate.start_epoch)
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

    limit_blockheight = pst.epoch * pst.deck.epoch_length

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

def update_voters(voters={}, new_cards=[], weight=1):
    # voter dict:
    # key: sender (address)
    # value: combined value of card_transfers (can be negative).
    # TODO: maybe we need to implement CardBurn as well,
    # which could be done with CardTransfer.
    # MODIFIED: added weight, this is for SDP voters.

    if weight != 1:
        for voter in voters:
           old_amount = voters[voter]
           voters.update({ voter : int(old_amount * weight) })

    for card in new_cards:

        for receiver in card.receiver:
            rec_position = card.receiver.index(receiver)
            rec_amount = int(card.amount[rec_position] * weight)

            if receiver not in voters:
                voters.update({receiver : rec_amount})
            else:
                # old_amount = int(voters[receiver] * weight)
                old_amount = voters[receiver]
                voters.update({receiver : old_amount + rec_amount})

        # if cardissue, we only add balances to receivers, nothing is deducted.
        # Donors have to send the CardIssue to themselves if they want their coins.
        if card.type == "CardTransfer":
            rest = int(-sum(card.amount) * weight)
            if card.sender not in voters:
                voters.update({card.sender : rest})
            else:
                old_amount = voters[card.sender]
                voters.update({receiver : old_amount + rest})

    return voters

def get_votes(pst, proposal, epoch):
    # returns a dictionary with two keys: "positive" and "negative",
    # containing the amounts of the tokens with whom an address was voted.
    # TODO: This is still without the "first vote can also be valid for second round" system.

    votes = {}
    for outcome in ("positive", "negative"):
       balance = 0
       try:
           vtxs = pst.voting_transactions[proposal.first_ptx.txid][outcome]
       except KeyError:
           votes.update({outcome : 0})
           continue
       for vote in vtxs:
           if vote.epoch == epoch:
                balance += pst.enabled_voters[vote.sender]
       votes.update({outcome : balance})

    return votes


