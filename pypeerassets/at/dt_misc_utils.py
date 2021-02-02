from pypeerassets.at.dt_entities import ProposalTransaction
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.at.dt_parser import ParserState, dt_parser
from pypeerassets.at.dt_parser_utils import get_votes
from pypeerassets.__main__ import get_card_bundles
from pypeerassets.provider import Provider
from pypeerassets.kutil import Kutil

def get_startendvalues(provider, proposal_txid, period):
    # TODO: Unittest for that (should be easy).
    # ./paclix transaction dt_vote 617005e36d23794763521ac3bad6d53a0ad6ee4259c8e45d8e81cdd09d67d595 81b042e652bd807ed2fd1cef069f90701a2fd1ae9385dc90cf69a5404a1f92e6 "+" --check_phase=1 --wait
    # result: phase_start: 484022 phase_end: 484044 epoch_length 22
    # This is mainly for PACLI. It returns the start and end block of the current period.
    # Periods have the following format: (PERIOD_TYPE, round/phase).
    # For example, the first voting phase is: ("voting", 0)
    # and the second dist_round for signalling is: ("signalling", 1)

    proposal_tx = ProposalTransaction.from_txid(proposal_txid, provider)
    # TODO: This still doesn't deal with Proposal Modifications. Will probably need a function get_last_proposal.
    p = ProposalState(first_ptx=proposal_tx, valid_ptx=proposal_tx, provider=provider)
    print("period", period)

    # TODO 2: Look if we can already implement the "voting only once and change vote" system (maybe we can simply go with the following rule for round 2: round 1 votes are added to round 2 votes, and only the last vote counts)
    if (period == ("voting", 0)) or (period[0] in ("signalling", "locking", "donation") and period[1] < 5):
        phase_start = p.dist_start # (p.start_epoch + 1) * p.deck.epoch_length
    else:
        phase_start = p.end_epoch * p.deck.epoch_length
    print("Dist start:", p.dist_start, phase_start)

    phase_end = phase_start + p.deck.epoch_length - 1

    print("phase_start:", phase_start, "phase_end:", phase_end, "epoch_length", p.deck.epoch_length)

    if period[0] == "voting":
        startblock = phase_start + p.security_periods[period[1]]
        endblock = startblock + p.voting_periods[period[1]] - 1
    elif period[0] == "signalling":
        startblock = p.round_starts[period[1]]
        endblock = p.round_halfway[period[1]] - 1
    elif period[0] in ("locking", "donation"):
        startblock = p.round_halfway[period[1]]
        endblock = min(p.round_starts[period[1] + 1], phase_end) - 1

    return {"start" : startblock, "end" : endblock}

def get_votestate(provider, proposal_txid, phase=0, debug=False):
    """Get the state of the votes of a Proposal without calling the parser completely."""
    
    current_blockheight = provider.getblockcount()
    ptx = ProposalTransaction.from_txid(proposal_txid, provider)
    # TODO: Does probably not deal with ProposalModifications still.
    pstate = ProposalState(first_ptx=ptx, valid_ptx=ptx, provider=provider)
    unfiltered_cards = list((card for batch in get_card_bundles(provider, ptx.deck) for card in batch))

    if phase == 0:
        lastblock = min(current_blockheight, pstate.dist_start)
    elif phase == 1:
        lastblock = min(current_blockheight, pstate.end_epoch * pstate.deck.epoch_length)
    else:
        raise ValueError("No correct phase number entered. Please enter 0 or 1.")
    # print("currentblock", lastblock)


    pst = ParserState(ptx.deck, unfiltered_cards, provider, current_blockheight=lastblock, debug=debug)

    valid_cards = dt_parser(unfiltered_cards, provider, lastblock, ptx.deck, debug=debug, initial_parser_state=pst, force_continue=True) # later add: force_dstates=True

    for p in pst.proposal_states.values():
        if p.first_ptx.txid == proposal_txid:
            proposal = p
            break
    else:
        print("Proposal based on transaction {} not found.".format(ptx))
        return None

    if phase == 0:
        epoch = proposal.dist_start // proposal.deck.epoch_length # start_epoch cannot be used as the voting phase is often in start_epoch + 1
    elif phase == 1:
        epoch = proposal.end_epoch
    # print("Checked epoch:", epoch, "dist_start", proposal.dist_start, "startep", proposal.start_epoch, "endep", proposal.end_epoch)
    votes = get_votes(pst, proposal, epoch, formatted_result=True)
    return votes


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
