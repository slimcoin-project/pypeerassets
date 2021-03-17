from pypeerassets.at.dt_entities import ProposalTransaction
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.at.dt_parser import ParserState, dt_parser
from pypeerassets.at.dt_parser_utils import get_votes
from pypeerassets.__main__ import get_card_bundles
from pypeerassets.provider import Provider
from pypeerassets.kutil import Kutil
from pypeerassets.transactions import make_raw_transaction, p2pkh_script, nulldata_script, MutableTxIn, TxIn, TxOut, Transaction, MutableTransaction, MutableTxIn, ScriptSig, Locktime
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, net_query
from pypeerassets.provider.rpcnode import Sequence
from decimal import Decimal
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from binascii import unhexlify

DEFAULT_P2TH_FEE = 1000000 # int value required # should be replaced with the minimum amount of net_query.
#DEFAULT_SEQUENCE = 0xffffffff # we use Sequence.max()
COIN = 100000000

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
        votes = proposal.initial_votes
    elif phase == 1:
        votes = proposal.final_votes

    return format_votes(pst.sdp_deck_obj.number_of_decimals, votes)

    #if phase == 0:
    #    epoch = proposal.dist_start // proposal.deck.epoch_length # start_epoch cannot be used as the voting phase is often in start_epoch + 1
    #elif phase == 1:
    #    epoch = proposal.end_epoch
    # print("Checked epoch:", epoch, "dist_start", proposal.dist_start, "startep", proposal.start_epoch, "endep", proposal.end_epoch)
    #votes = get_votes(pst, proposal, epoch, formatted_result=True)

    # return votes

def format_votes(decimals, votes):
    fvotes = {}
    for outcome in ["positive", "negative"]:
        balance = Decimal(votes[outcome]) / 10**decimals
        fvotes.update({outcome : balance})
    return fvotes


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


### Unsigned transactions

# could also use p2pkh_script(network: str, address: str) from pypeerassets.transactions

def create_p2pkh_txout(value: int, address: str, n: int, network="tppc"):
    #address = Address.from_string(addr_string)
    #script = P2pkhScript(address)
    script = p2pkh_script(network, address)
    return TxOut(value=value, n=n, script_pubkey=script, network=network)

def create_cltv_txout():
    # TODO: Create output for locking transaction.
    pass

def create_p2th_txout(deck, tx_type, fee=DEFAULT_P2TH_FEE, network="tppc"):
    # Warning: always creates the p2th out at n=0.
    p2th_addr = deck.derived_p2th_address(tx_type)
    return create_p2pkh_txout(value=fee, address=p2th_addr, n=0, network=network)

def create_opreturn_txout(tx_type: str, data: bytes, network="tppc"):
    # Warning: always creates the opreturn out at n=1.
    #data = datastr.encode("utf-8")
    script = nulldata_script(data)
    return TxOut(value=0, n=1, script_pubkey=script, network=network)


def create_unsigned_tx(deck, address, amount, provider, tx_type, data, network="tppc", version=1, change_address=None, tx_fee=None, input_txid=None, input_vout=None, input_address=None, locktime=0, cltv_timelock=0):

    try:
        if not tx_fee:
            network_params = net_query(network)
            tx_fee = int(network_params.min_tx_fee * COIN) # this is rough, as it is min_tx_fee per kB, but a TrackedTransaction should only seldom have more than 1 kB.
        p2th_output = create_p2th_txout(deck, tx_type)
        data_output = create_opreturn_txout(tx_type, data)
        if tx_type == "locking":
            value_output = create_cltv_txout(amount, address, 2, cltv_timelock)
        else:
            value_output = create_p2pkh_txout(amount, address, 2)

        outputs = [p2th_output, data_output, value_output]
        complete_amount = p2th_output.value + amount + tx_fee
        #if (input_txid is not None) and (input_vout is not None):
        if None not in (input_txid, input_vout):
            input_tx = provider.getrawtransaction(input_txid, 1)
            inp_output = input_tx["vout"][input_vout]
            inp = MutableTxIn(txid=input_txid, txout=input_vout, script_sig=ScriptSig.empty(), sequence=Sequence.max())
            inputs = [inp]
            input_value = int(input_tx["vout"][input_vout]["value"] * COIN)
        elif input_address:
            dec_complete_amount = Decimal(complete_amount / COIN)
            input_query = provider.select_inputs(input_address, dec_complete_amount)
            inputs = input_query["utxos"]
            input_value = int(input_query["total"] * COIN)
            inp = inputs[0] # check!
        else:
            return None
        
        change_value = input_value - complete_amount
        print(complete_amount, change_value, input_value)
        #change_value = complete_amount - sum([i.value for i in inputs])

        # Look if there is change, if yes, create fourth output.
        # TODO: Could be improved if an option creates a higher tx fee when the rest is dust.

        if change_value > 0:
            # If no change address is delivered we use the address from the input.
            print(inp, inp.script_sig)
            if change_address is None:
                if input_address is None:
                    change_address = inp_output['scriptPubKey']['addresses'][0]
                else:
                    change_address = input_address
            change_output = create_p2pkh_txout(change_value, change_address, 3)
            outputs.append(change_output)
        elif change_value < 0:
            raise Exception("Not enough funds in the input transaction.")

        unsigned_tx = make_raw_transaction(network=network,
                                       inputs=inputs,
                                       outputs=outputs,
                                       locktime=Locktime(locktime)
                                       )

        return unsigned_tx

    except IndexError: # (IndexError, AttributeError, ValueError):
        raise InvalidTrackedTransactionError("Invalid Transaction creation.")
