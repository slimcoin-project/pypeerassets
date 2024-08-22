# This file contains minor functions for the DT parser.

from decimal import Decimal

from pypeerassets.at.dt_entities import ProposalTransaction #, SignallingTransaction, DonationTransaction, LockingTransaction, VotingTransaction
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError # , DONATION_OUTPUT, DATASTR_OUTPUT
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.provider import Provider
from pypeerassets.pa_constants import param_query

### Transaction retrieval

def get_marked_txes(provider, p2th_account, min_blockheight=None, max_blockheight=None):
    # Gets all txes sent to a P2TH address, looping through "listtransactions".
    # As listtransactions may lead to duplicates, we filter them out with set.
    # Re-check speed.

    if min_blockheight is not None:
        min_blocktime = provider.getblock(provider.getblockhash(min_blockheight))["time"]
    if max_blockheight is not None:
        max_blocktime = provider.getblock(provider.getblockhash(max_blockheight))["time"]
    tx_tuple_list = []
    start = 0

    while True:
        # newtxes = provider.listtransactions(p2th_account, 999, start)
        newtxes = provider.listtransactions(account=p2th_account, many=999, since=start)
        for tx in newtxes:
           try:
               tx_blocktime = tx["blocktime"]
           except KeyError:
               # we need a fallback for legacy coins which do not offer blocktime parameter in listtransactions
               try:
                   blockhash = tx["blockhash"]
               except KeyError: # unconfirmed transactions are ignored
                   continue
               tx_blocktime = provider.getblock(blockhash)["time"]

           if max_blockheight:
              if tx_blocktime > max_blocktime:
                  continue
           if min_blockheight:
              if tx_blocktime < min_blocktime:
                  continue

           try:
               blockseq = tx["blockindex"]
           except KeyError:
               # fallback, if blockindex doesn't work.
               # we can unfortunately currently not use pautils.tx_serialization_order due to circular import.
               blockseq = provider.getblock(blockhash, decode=True)["tx"].index(tx["txid"])

           tx_tuple_list.append((tx["txid"], tx_blocktime, blockseq))

        if len(newtxes) < 999: # this means we reached the end.
            # Duplicates filtering
            ordered_txes = list(set(tx_tuple_list))
            # Sorting transactions by blocktime and position in the block, like we sort cards.
            ordered_txes.sort(key=lambda x: (x[1], x[2]))
            # this is the model: cards.sort(key=lambda x: (x.blocknum, x.blockseq, x.cardseq))
            txlist = [ provider.getrawtransaction(t[0], 1) for t in ordered_txes ]
            return txlist
        start += 999

def get_proposal_states(provider, deck, current_blockheight=None, all_signalling_txes=[], all_donation_txes=[], all_locking_txes=[], debug=False):
    # Gets all proposal txes of a deck and creates the initial ProposalStates. Needs P2TH.
    # If a new Proposal Transaction referencing an earlier one is found, the ProposalState is modified.
    # If provided, then donation/signalling txes are calculated
    statedict = {}
    used_firsttxids = []

    # p2th_account = deck.derived_p2th_address("proposal") # OLD behaviour
    p2th_account = deck.id + "PROPOSAL"
    for rawtx in get_marked_txes(provider, p2th_account):
        try:
            if debug:
                print("PARSER: Found ProposalTransaction", rawtx["txid"])
            tx = ProposalTransaction.from_json(tx_json=rawtx, provider=provider, deck=deck)

            if tx.txid in used_firsttxids: # filters duplicates
                if debug:
                    print("Ignoring duplicate proposal.")
                continue

            if debug:
                print("PARSER: Basic validity/duplicate check passed. First ptx: >{}<".format(tx.txid, tx.first_ptx_txid))

            if (tx.first_ptx_txid in ("", None, tx.txid)): # case 1: new proposal transaction
                state = ProposalState(first_ptx=tx, valid_ptx=tx, all_signalling_txes=all_signalling_txes, all_donation_txes=all_donation_txes, all_locking_txes=all_locking_txes)
                statedict.update({ tx.txid : state })

            elif tx.first_ptx_txid in statedict: # case 2: proposal modification
                state = statedict[tx.first_ptx_txid]

                if state.first_ptx.donation_address == tx.donation_address:
                    state.valid_ptx = tx
                    if debug:
                        print("PARSER: Proposal modification: added to proposal state {}".format(tx.first_ptx_txid))
                else:
                    if debug:
                        print("PARSER: Invalid modification: different donation address.")
                        print("PARSER: First ptx: {}, modification: {}".format(state.first_ptx.donation_address, tx.donation_address))
                    continue
            else: # case 3: invalid first ptx
                if debug:
                    print("PARSER: Invalid modification, invalid transaction format or non-existing proposal.")
                continue

        except InvalidTrackedTransactionError as e:
            print(e)
            continue

        used_firsttxids.append(tx.txid)

    return statedict

## SDP (mandatory for now)

def get_sdp_weight(epochs_from_start: int, sdp_periods: int) -> Decimal:
    # Weight calculation for SDP token holders
    # This function rounds percentages, to avoid problems with period lengths like 3.
    # (e.g. if there are 3 SDP epochs, last epoch will have weight 0.33)
    # IMPROVEMENT: Maybe it would make sense if this gives an int value which later is divided into 100,
    # because anyway there must be some rounding being done.
    # TODO: can maybe optimized with * 0.01 instead of / 100
    # return (Decimal((sdp_periods - epochs_from_start) * 100) // sdp_periods) / 100
    return (Decimal((sdp_periods - epochs_from_start) * 100) // sdp_periods) * Decimal("0.01")

### Voting

def update_sdp_weight(voters: dict, weight: Decimal, dec_diff: int=0, debug: bool=False) -> None:
   """After an epoch with completed proposals is recorded, the SDP weight is changed."""

   dec_adjustment = Decimal(10 ** dec_diff)

   # MODIFIED: Adjustment to get rounding to the precision of the voting token.
   for voter in voters:
       old_amount = Decimal(voters[voter]) / dec_adjustment
       new_amount = int(old_amount * weight) * dec_adjustment
       voters.update({voter : new_amount})

   if debug: print("Updating SDP balance of voter {}: {} to {}. Weight: {}".format(voter, old_amount * dec_adjustment, voters[voter], weight))

def update_voters(voters: dict, new_cards: list, weight: Decimal=Decimal("1"), dec_diff: int=0, debug: bool=False) -> None:
    """Updates voters when they are affected by a Card transfer (of any type)."""

    # It is only be applied to new_cards if they're SDP cards (as these are the SDP cards added).
    # voter dict:
    # key: sender (address)
    # value: combined value of card_transfers (can be negative).
    # The dec_diff value is the difference between number_of_decimals of main deck/sdp deck.
    # dec_diff isn't applied to old voters, thus it cannot be merged with "weight".

    # dec_adjustment has to be Decimal, because dec_diff can be negative
    dec_adjustment = Decimal(10 ** dec_diff)

    # 1. Update cards of old SDP voters by weight. # NO!
    """if weight != 1:

        for voter in voters:

           # MODIFIED: Adjustment to get rounding to the precision of the voting token.
           old_amount = Decimal(voters[voter]) / dec_adjustment
           new_amount = int(old_amount * weight) * dec_adjustment
           voters.update({voter : new_amount})

           if debug: print("Updating SDP balance of voter {}: {} to {}. Weight: {}".format(voter, old_amount * dec_adjustment, voters[voter], weight))"""

    # 2. Add votes of new cards
    for card in new_cards:
        if debug: print("Card data:", card.txid, card.sender, card.receiver, card.amount, card.type)

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
                if debug: print("Card sender {} not in voters. Resting the rest: {}".format(card.sender, rest * dec_adjustment))
                voters.update({card.sender : rest * dec_adjustment})
            else:
                old_amount = voters[card.sender]
                if debug: print("Card sender {} updated from: {} to: {}".format(card.sender, old_amount, old_amount + rest * dec_adjustment))
                voters.update({card.sender : old_amount + rest * dec_adjustment})

    return voters
