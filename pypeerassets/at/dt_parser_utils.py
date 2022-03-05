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

def get_marked_txes(provider, p2th_account, min_blockheight=None, max_blockheight=None):
    # basic function. Gets all txes sent to a P2TH address, looping through "listtransactions".
    # This needs before the address being imported into the coin wallet, and the account being set to its name.
    # (see import_p2th_address)

    if min_blockheight is not None:
        min_blocktime = provider.getblock(provider.getblockhash(min_blockheight))["time"]
    if max_blockheight is not None:
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
            # print("tx checked:", tx.txid, "first ptx", tx.first_ptx_txid)
            """if tx.txid not in used_firsttxids:
                state = ProposalState(first_ptx=tx, valid_ptx=tx, current_blockheight=current_blockheight, all_signalling_txes=all_signalling_txes, all_donation_txes=all_donation_txes, all_locking_txes=all_locking_txes, provider=provider)
            else:
                state = statedict[tx.txid]
                if state.first_ptx.txid == tx.first_ptx_txid:
                    state.valid_ptx = tx # TODO: This could need an additional validation step, although it is unlikely it can be used for attacks.
                else:
                    continue"""

            if tx.txid not in used_firsttxids: # filters out duplicates
                if (tx.first_ptx_txid in (None, tx.txid)) or len(tx.first_ptx_txid) != 64: # case 1: new proposal transaction # TODO: extra condition added for invalid proposals!
                    state = ProposalState(first_ptx=tx, valid_ptx=tx, current_blockheight=current_blockheight, all_signalling_txes=all_signalling_txes, all_donation_txes=all_donation_txes, all_locking_txes=all_locking_txes, provider=provider)
                elif tx.first_ptx_txid in statedict: # case 2: proposal modification
                    state = statedict[tx.first_ptx_txid]
                    if state.first_ptx.donation_address == tx.donation_address:
                        state.valid_ptx = tx
                else: # case 3: invalid first ptx
                    continue
            else: # case 4: duplicate
                continue

        except InvalidTrackedTransactionError as e:
            print(e)
            continue

        statedict.update({ tx.txid : state })
        used_firsttxids.append(tx.txid)
        # print("updated state", tx.txid)

    return statedict

## SDP
# TODO: What if there is no SDP token defined? Somebody must vote in the first round.
# An idea could be to use burn transactions in the last epoch (if it's the first epoch, then it would be simply "counting backwards") -> but this would encourage burning perhaps too much
# second idea: the deck issuer could vote for the first Proposal, or define the voters. However, this would make the token have a centralized element.
# "all proposals are voted" or "voting by the donors" are not possible as they have a risk of cheating.
# maybe best is make SDP mandatory.

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

### Other utils

def deck_from_tx(txid: str, provider: Provider, deck_version: int=1, prod: bool=True):
    '''Wrapper for deck_parser, gets the deck from the TXID.'''
    # NOTE: at a first glance this may fit better in dt_misc_utils, but then it throws a circular import.
    from pypeerassets.pautils import deck_parser

    params = param_query(provider.network)
    p2th = params.P2TH_addr
    raw_tx = provider.getrawtransaction(txid, 1)
    # vout = raw_tx["vout"][0]["scriptPubKey"].get("addresses")[0] ???
    deck = deck_parser((provider, raw_tx, deck_version, p2th), prod)
    return deck
