# This file contains minor functions for the DT parser.

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction, ProposalState, SignallingTransaction, DonationTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError, DONATION_OUTPUT, DATASTR_OUTPUT
from pypeerassets.at.transaction_formats import *


# modified: constants went to at_transaction_formats

### Address and P2TH tools

def import_p2th_address(provider, p2th_address):
    # this checks if a P2TH address is already imported. If not, import it (only rpcnode).
    p2th_account = provider.getaccount(p2th_address)
    #print(p2th_account)
    if (p2th_account is None) or (p2th_account != p2th_address):
        provider.importaddress(p2th_address)
        provider.setaccount(p2th_address, p2th_address) # address is also the account name.


def dt_tracked_address(card_issue):
    # this one extracts proposal transaction from asset_specific_data and extracts the address.
    address = card_issue.asset_specific_data[COIN_ISSUE_DT_FORMAT["donation_tx"]:COIN_ISSUE_DT_FORMAT["vout"]]
    return address

def deck_p2th_from_id(network, deck_id):
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
        min_blocktime = provider.getblockheader(provider.getblockhash(min_blockheight))["time"]
    if max_blockheight:
        max_blocktime = provider.getblockheader(provider.getblockhash(max_blockheight))["time"]
    txlist = []
    start = 0
    while True:
        newtxes = provider.listtransactions(p2th_account, 999, start)
        for tx in newtxes:
           if max_blockheight or min_blockheight:
              if (tx["blocktime"] > max_blocktime) or (tx["blocktime"] < min_blocktime):
                  continue
           
           txlist.append(provider.getrawtransaction(tx["txid"], 1))

        if len(newtxes) < 999: # lower than limit
            return txlist
        start += 999

def get_donation_txes(provider, deck):
    # gets ALL donation txes of a deck. Needs P2TH.
    # TODO: look if this makes sense:
    # if Proposal is given, then the dtx are already added to the proposal.
    # TODO: or the other way round: Proposal should be added already here to each DonationTransaction.
    # Would need to be passed as an argument.
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("donation")):
        try:
            print("Creating transaction object...")
            tx = DonationTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
            #if proposal_state:
            #    proposal_state.donation_txes.append(tx)
        except InvalidTrackedTransactionError:
            continue
        txlist.append(tx)
    return txlist

def get_signalling_txes(provider, deck):
    # gets ALL signalling txes of a deck. Needs P2TH.
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("signalling")):
        try:
            print("Creating transaction object...")
            tx = SignallingTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
        except InvalidTrackedTransactionError:
            continue
        txlist.append(tx)
    return txlist

def get_proposal_txes(provider, deck):
    # gets ALL proposal txes of a deck. Needs P2TH.
    txlist = []
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("proposal")):
        try:
            tx = ProposalTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)
        except InvalidTrackedTransactionError:
            continue
        txlist.append(tx)
    return txlist

def get_voting_txes(provider, deck):
    # gets ALL proposal txes of a deck. Needs P2TH.
    # uses a dict to group votes by proposal and by outcome ("positive" and "negative")
    # b'+' is the value for a positive vote, b'-' is negative, others are invalid.
    txdict = {}
    for rawtx in get_marked_txes(provider, deck.derived_p2th_address("voting")):

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

            if proposal_txid in txdict:
                txdict[proposal_txid].update({ outcome : tx })
            else:
                txdict.update({ proposal_txid : { outcome : tx }})

    return txdict

def get_proposal_states(provider, deck, current_blockheight=None, all_signalling_txes=None, all_donation_txes=None):
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
                state = ProposalState(first_ptx=tx, valid_ptx=tx, current_blockheight=current_blockheight, all_signalling_txes=all_signalling_txes, all_donation_txes=all_donation_txes, provider=provider)

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

    for pstate in proposal_states.values(): # proposal_states is dict.
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

    return valid_proposals

def was_vout_moved(provider, dtx):
    # we need move_txid from asset_specific_data.
    # TODO: We need to make sure that the tx was signed with the private key of the Proposer, not the key of the Donor.
    # This is perhaps already achieved with the check for the output, but if_else structure has to be re-checked.
    move_tx = provider.getrawtransaction(dtx.move_txid)

    for vin in move_tx["vin"]:
        if vin["txid"] == dtx.txid and vin["vout"] == 2:
            return True

    return False

def get_proposal_factor(pst, proposal_state):
    # Proposal factor: if there is more than one proposal ending in the same epoch,
    # the resulting slot is divided by the req_amounts of them.

    ending_proposals = [p for p in pst.valid_proposals.values() if p.end_epoch == proposal_state.end_epoch]
    if pst.debug: print("Ending proposals in the same epoch than the one referenced here:", ending_proposals)

    if len(ending_proposals) > 1:
        total_req_amount = sum([p.req_amount for p in ending_proposals])
        proposal_factor = Decimal(proposal_state.req_amount) / total_req_amount
    else:
        proposal_factor = 1

    if pst.debug: print("Proposal factor", proposal_factor)

    return proposal_factor

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

def get_sdp_weight(epochs_from_start, sdp_periods):
    # Weight calculation for SDP token holders
    # This function rounds percentages, to avoid problems with period lengths like 3.
    # (e.g. if there are 3 SDP epochs, last epoch will have weight 0.33)
    return ((sdp_periods - epochs_from_start) * 100 // sdp_periods) * 100

### Voting

def update_voters(voters={}, new_cards=[], weight=1):
    # voter dict:
    # key: sender (address)
    # value: combined value of card_transfers (can be negative).
    # TODO: maybe we need to implement CardBurn as well,
    # which could be done with CardTransfer.
    # MODIFIED: added weight, this is for SDP voters.

    for card in new_cards:

        for receiver in card.receiver:
            rec_position = card.receiver.index(receiver)
            rec_amount = card.amount[rec_position] * weight

            if receiver not in voters:
                voters.update({receiver : rec_amount})
            else:
                old_amount = voters[receiver] * weight
                voters.update({receiver : old_amount + rec_amount})

        # if cardissue, we only add balances to receivers, nothing is deducted.
        # Donors have to send the CardIssue to themselves if they want their coins.
        if card.type == "CardTransfer":
            if card.sender not in voters:
                voters.update({card.sender : -sum(card.amount) * weight})
            else:
                old_amount = voters[card.sender] * weight
                voters.update({receiver : old_amount - sum(card.amount) * weight})

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

## slot allocation


def get_raw_slot(tx, req_amount, slot_rest=0, total_amount=None, round_txes=None):
    # calculates the slot (maximum donation amount which gets translated into tokens) in a round (rd1-3/5-6))
    # Important: This is NOT the token amount the donor gets, but the maximum proportion of the token amount per distribution round.
    # step 1: get signalling txes in round.
    # MODIFIED: optimized, so no heavy calculations are done always if total_amount is known

    if (total_amount is None) and round_txes:
        total_amount = sum([tx.amount for tx in round_txes])

    print("Total amount", total_amount, "TX amount", tx.amount, "REQ amount", req_amount, "slot rest", slot_rest)
    tx_proportion = Decimal(tx.amount) / total_amount

    if slot_rest == 0:
        max_slot = req_amount * tx_proportion
    else:
        max_slot = slot_rest * tx_proportion

    print("Proportion", tx_proportion, "Max slot", max_slot)

    # maximum slot is the transaction amount
    return min(tx.amount, max_slot)

def get_first_serve_slot(stx, round_txes, slot_rest=Decimal(0)):
    # assumes chronological order of txes.
    try:
        stx_pos = round.txes.index(stx)
        amounts_to_stx = [ tx.signalled_amount for tx in round_txes[:stx_pos] ]
        if sum(amounts_to_stx) < slot_rest:
            return tx.signalled_amount
        else:
            return 0
 
    except IndexError:
        return 0

def get_slot(tx, proposal_state, round_txes, dist_round):

    # SIMPLIFIED version without prioritary groups (see below).
    # slot distribution. Needs to be done by round, as rules are pretty different in each of them.
    
    # first 4 rounds require timelocks, so locked_amounts must be initalized.
    # This is only necessary if there were donations in the first phase.

    print("All normal signalled amounts", proposal_state.signalled_amounts)
    print("Dist round of current tx:", dist_round)
    
    if dist_round in (0, 1, 2, 3):
        req_amount = proposal_state.first_ptx.req_amount
        
        if not proposal_state.locked_amounts:
            proposal_state.locked_amounts = [0, 0, 0, 0]

        if dist_round == 0:
            return get_raw_slot(tx, req_amount, total_amount=proposal_state.signalled_amounts[0])   

        slot_rest_rd0 = req_amount - proposal_state.locked_amounts[0]

        if dist_round == 1:
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd0, total_amount=proposal_state.signalled_amounts[1])

        slot_rest_rd1 = slot_rest_rd1 - proposal_state.locked_amounts[1]
    
        if dist_round == 2:
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd0, total_amount=proposal_state.signalled_amounts[2])

        slot_rest_rd2 = slot_rest_rd2 - proposal_state.locked_amounts[2]

        if dist_round == 3:
            return get_first_serve_slot(tx, proposal_state.signalling_txes[3], slot_rest=slot_rest_rd2)

    elif dist_round in (4, 5, 6, 7):
        # For second phase, we take the last valid Proposal Transaction to calculate slot, not the first one.
        req_amount = proposal_state.valid_ptx.req_amount

        not_donated_amount = req_amount - sum(proposal_state.donated_amounts[:3])
        print("Not donated amount", not_donated_amount)

        if dist_round == 4:        
            return get_raw_slot(tx, req_amount, slot_rest=not_donated_amount, total_amount=proposal_state.signalled_amounts[4])

        slot_rest_rd4 = not_donated_amount - proposal_state.donated_amounts[4]

        if dist_round == 5:
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd4, total_amount=proposal_state.signalled_amounts[5])

        slot_rest_rd5 = not_donated_amount - sum(proposal_state.donated_amounts[4:6])

        if dist_round == 6:        
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd5, total_amount=proposal_state.signalled_amounts[6])

        slot_rest_rd6 = not_donated_amount - sum(proposal_state.donated_amounts[4:7])

        if dist_round == 7:        
            return get_first_serve_slot(tx, proposal_state.signalling_txes[7], slot_rest=slot_rest_rd6)

    return None # if dist_round is incorrect


def get_slot_new(tx, proposal_state, round_txes, dist_round):
    # TODO: This is the variant with prioritary groups in round 2/3 and 5/6/7.
    # slot distribution. Needs to be done by round, as rules are pretty different in each of them.

    # TODO: PRIORITARY GROUP implementation (round 2/3 in phase1 and 5/6/7 in phase2).
    # instead of signalling transaction, it would be better to work with signalling outputs (because of the slot 2-3/slot 6/7 rules).
    # -> the thing is that people signalling with ReservedAmounts should not need to create another signalling tx.
    # thus, we need to change the algorithm so a prior DonationTransaction can also be used for signalling.
    # first, slot is calculated according to reserved amounts.
    
    # first 4 rounds require timelocks, so locked_amounts must be initalized.
    # This is only necessary if there were donations in the first phase.

    print("All normal signalled amounts", proposal_state.signalled_amounts)
    print("Dist round of current tx:", dist_round)
    
    if dist_round in (0, 1, 2, 3):
        req_amount = proposal_state.first_ptx.req_amount
        
        if not proposal_state.locked_amounts:
            proposal_state.locked_amounts = [0, 0, 0, 0]

        if dist_round == 0:
            return get_raw_slot(tx, req_amount, total_amount=proposal_state.signalled_amounts[0])   

        slot_rest_rd0 = req_amount - proposal_state.locked_amounts[0]

        if dist_round == 1:
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd0, total_amount=proposal_state.signalled_amounts[1])

        slot_rest_rd1 = slot_rest_rd1 - proposal_state.locked_amounts[1]
    
        if dist_round == 2:
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd0, total_amount=proposal_state.signalled_amounts[2])

        slot_rest_rd2 = slot_rest_rd2 - proposal_state.locked_amounts[2]

        if dist_round == 3:
            return get_first_serve_slot(tx, proposal_state.signalling_txes[3], slot_rest=slot_rest_rd2)

    elif dist_round in (4, 5, 6, 7):
        # For second phase, we take the last valid Proposal Transaction to calculate slot, not the first one.
        req_amount = proposal_state.valid_ptx.req_amount

        not_donated_amount = req_amount - sum(proposal_state.donated_amounts[:3])
        print("Not donated amount", not_donated_amount)

        if dist_round == 4:        
            return get_raw_slot(tx, req_amount, slot_rest=not_donated_amount, total_amount=proposal_state.signalled_amounts[4])

        slot_rest_rd4 = not_donated_amount - proposal_state.donated_amounts[4]

        if dist_round == 5:
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd4, total_amount=proposal_state.signalled_amounts[5])

        slot_rest_rd5 = not_donated_amount - sum(proposal_state.donated_amounts[4:6])

        if dist_round == 6:        
            return get_raw_slot(tx, req_amount, slot_rest=slot_rest_rd5, total_amount=proposal_state.signalled_amounts[6])

        slot_rest_rd6 = not_donated_amount - sum(proposal_state.donated_amounts[4:7])

        if dist_round == 7:        
            return get_first_serve_slot(tx, proposal_state.signalling_txes[7], slot_rest=slot_rest_rd6)

    return None # if dist_round is incorrect
