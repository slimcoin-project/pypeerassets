from pypeerassets.at.dt_entities import ProposalTransaction, DonationTimeLockScript
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.at.dt_parser import ParserState, dt_parser
from pypeerassets.at.dt_parser_utils import get_votes
from pypeerassets.__main__ import get_card_bundles
from pypeerassets.provider import Provider
from pypeerassets.protocol import Deck
from pypeerassets.kutil import Kutil
from pypeerassets.transactions import make_raw_transaction, p2pkh_script, nulldata_script, MutableTxIn, TxIn, TxOut, Transaction, MutableTransaction, MutableTxIn, ScriptSig, Locktime
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, net_query
from pypeerassets.provider.rpcnode import Sequence
from btcpy.structs.address import P2shAddress
from btcpy.structs.script import P2shScript
from decimal import Decimal
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from binascii import unhexlify

DEFAULT_P2TH_FEE = Decimal('0.01')

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

    proposal = get_proposal_state(provider, proposal_txid, phase=phase, debug=debug)

    if phase == 0:
        votes = proposal.initial_votes
    elif phase == 1:
        votes = proposal.final_votes

    return format_votes(proposal.deck.number_of_decimals, votes)

def get_dstate_from_txid(txid: str, proposal_state: ProposalState):
    # returns donation state from a signalling, locking or donation transaction.

    for ds in proposal_state.donation_states:
        if txid in (ds.signalling_tx.txid, ds.locking_tx.txid, ds.reserve_tx.txid, ds.donation_tx.txid):
            return ds
    else:
        return None

def get_dstates_from_address(address: str, proposal_state: ProposalState, dist_round: int=None):
    # returns donation state from a signalling, locking or donation transaction.
    # Uses the destination address, which is the address from which the donor will do locking/donation.

    states = []
    print("Donation states:", proposal_state.donation_states)
    for rd in proposal_state.donation_states:
        for ds in rd.values():
            for tx in [ ds.signalling_tx, ds.locking_tx, ds.reserve_tx ]:
               if tx is None:
                   continue
               try:
                   tx_addr = tx.reserve_address.__str__()
               except AttributeError: # SignallingTX
                   tx_addr = tx.address.__str__()
                   print(tx_addr, address)
               if tx_addr == address:
                   states.append(ds)

    return states

def get_donation_state(provider, proposal_id=None, proposal_tx=None, tx_txid=None, address=None, phase=0, debug=False, dist_round=0, pos=None):

    proposal_state = get_proposal_state(provider, proposal_id=proposal_id, proposal_tx=proposal_tx, phase=phase, debug=debug)

    ## following section probably not necessary.
    #if tx_type == "signalling":
    #     txes = proposal.all_signalling_transactions
    #elif tx_type == "locking":
    #     txes = proposal.all_locking_transactions
    #elif tx_type == "donation":
    #     txes = proposal.all_donation_transactions

    #for tx in txes:
    #    if tx.txid == tx_txid:
    #        break
    #else:
    #    raise Exception("Transaction not found.")

    if tx_txid is not None:
        result = get_dstate_from_txid(txid, proposal_state)
    elif address is not None:
        states = get_dstates_from_address(address, proposal_state, dist_round=dist_round)
        if debug: print("All donation states for address {}:".format(address), states)
        if pos is not None:
            try:
                result = states[pos]
            except IndexError:
                result = None
        else:
            result = states
         
    else:
        result = [ s for rd in proposal_state.donation_states for s in rd ]
 
    return result

def get_proposal_state(provider, proposal_id=None, proposal_tx=None, phase=0, debug=False):

    current_blockheight = provider.getblockcount()
    if not proposal_tx:
        ptx = ProposalTransaction.from_txid(proposal_id, provider)
    else:
        ptx = proposal_tx
        proposal_id = ptx.txid
    # TODO: Does probably not deal with ProposalModifications still.
    pstate = ProposalState(first_ptx=ptx, valid_ptx=ptx, provider=provider)

    if debug: print("Deck:", pstate.deck.id)

    unfiltered_cards = list((card for batch in get_card_bundles(provider, ptx.deck) for card in batch))

    if phase == 0:
        lastblock = min(current_blockheight, pstate.dist_start)
    elif phase == 1:
        lastblock = min(current_blockheight, pstate.end_epoch * pstate.deck.epoch_length)
    else:
        raise ValueError("No correct phase number entered. Please enter 0 or 1.")

    pst = ParserState(ptx.deck, unfiltered_cards, provider, current_blockheight=lastblock, debug=debug)

    valid_cards = dt_parser(unfiltered_cards, provider, lastblock, ptx.deck, debug=debug, initial_parser_state=pst, force_continue=True, force_dstates=True) # later add: force_dstates=True

    #if phase == 0:
    #    epoch = proposal.dist_start // proposal.deck.epoch_length # start_epoch cannot be used as the voting phase is often in start_epoch + 1
    #elif phase == 1:
    #    epoch = proposal.end_epoch
    # print("Checked epoch:", epoch, "dist_start", proposal.dist_start, "startep", proposal.start_epoch, "endep", proposal.end_epoch)
    #votes = get_votes(pst, proposal, epoch, formatted_result=True)

    # return votes

    for p in pst.proposal_states.values():
        if debug: print("Checking proposal:", p.first_ptx.txid)
        if p.first_ptx.txid == proposal_id:
            proposal = p
            break
    else:
        print("Proposal based on transaction {} not found.".format(ptx.txid))
        return None

    return proposal

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


### Unsigned transactions and P2SH

def create_p2pkh_txout(value: int, address: str, n: int, network=PeercoinTestnet):
    #address = Address.from_string(addr_string)
    #script = P2pkhScript(address)
    #print("network", network)
    script = p2pkh_script(network.shortname, address) # we need the shortname here
    return TxOut(value=value, n=n, script_pubkey=script, network=network)

# not working properly, creates nonstandard tx, p2sh is needed!
#def create_cltv_txout(value: int, address: str, n: int, timelock: int, network=PeercoinTestnet):
#    print("Network", network, "Addr", address)
#    script = DonationTimeLockScript(raw_locktime=timelock, dest_address_string=address, network=network)
#    return TxOut(value=value, n=n, script_pubkey=script, network=network)

def create_p2sh_txout(value: int, redeem_script: DonationTimeLockScript, n: int, network=PeercoinTestnet):
    p2sh_script = P2shScript(redeem_script)
    return TxOut(value=value, n=n, script_pubkey=p2sh_script, network=network)

def create_redeem_script(address: str, timelock: int, network=PeercoinTestnet):
    script = DonationTimeLockScript(raw_locktime=timelock, dest_address_string=address, network=network)
    return script

def create_p2sh_address(redeem_script: DonationTimeLockScript, network=PeercoinTestnet):
    p2sh_script = P2shScript(redeem_script)
    print(p2sh_script)
    print(redeem_script)
    addr = P2shAddress.from_script(redeem_script, network=network)
    return addr

def create_p2th_txout(deck, tx_type, fee, network=PeercoinTestnet):
    # Warning: always creates the p2th out at n=0.
    p2th_addr = deck.derived_p2th_address(tx_type)
    return create_p2pkh_txout(value=fee, address=p2th_addr, n=0, network=network)

def create_opreturn_txout(tx_type: str, data: bytes, network=PeercoinTestnet):
    # Warning: always creates the opreturn out at n=1.
    #data = datastr.encode("utf-8")
    script = nulldata_script(data)
    return TxOut(value=0, n=1, script_pubkey=script, network=network)


def create_unsigned_tx(deck: Deck, provider: Provider, tx_type: str, amount: int=None, proposal_txid: str=None, data: bytes=None, address: str=None, network=PeercoinTestnet, version: int=1, change_address: str=None, tx_fee: int=None, p2th_fee: int=None, input_txid: str=None, input_vout: int=None, input_address: str=None, locktime: int=0, cltv_timelock: int=0):

    if tx_type != "proposal":
        if data and (not proposal_txid):
            proposal_txid = str(data[2:34].hex())

    try:
        network_params = net_query(network.shortname) # Could be unnecessary.
        coin = int(Decimal(1) / network_params.from_unit)
        if not tx_fee:            
            tx_fee = int(network_params.min_tx_fee) * coin # this is rough, as it is min_tx_fee per kB, but a TrackedTransaction should only seldom have more than 1 kB.
        if not p2th_fee:
            p2th_fee = int(coin * DEFAULT_P2TH_FEE)

        p2th_output = create_p2th_txout(deck, tx_type, fee=p2th_fee)
        data_output = create_opreturn_txout(tx_type, data)
        if (address == None) and (tx_type == "donation"):
            ptx = ProposalTransaction.from_txid(proposal_txid, provider)
            address = ptx.donation_address

        outputs = [p2th_output, data_output]
        if tx_type == "locking":
            # First create redeem script, then P2SH address, then the output spending to that script.
            redeem_script = create_redeem_script(address=address, timelock=cltv_timelock, network=network)
            p2sh_script = P2shScript(redeem_script)
            p2sh_addr = create_p2sh_address(redeem_script, network=network)
            print("P2SH address for this Locking Transaction:", p2sh_addr)
            print("You will need the keys for address", address, "to spend funds.")
            p2sh_output = create_p2sh_txout(amount, p2sh_script, n=2, network=network)
            # p2pkh_output = create_p2pkh_txout(amount, p2sh_addr.__str__(), 2)
            outputs.append(p2sh_output)
            # outputs.append(create_cltv_txout(value=amount, address=address, n=2, timelock=cltv_timelock))
        elif tx_type in ("signalling", "donation"):
            outputs.append(create_p2pkh_txout(amount, address, 2))
        else:
            amount = 0 # proposal and vote types do not have amount.

        complete_amount = p2th_output.value + amount + tx_fee
        print("p2v", p2th_output.value, amount, tx_fee, type(p2th_output.value))
        #if (input_txid is not None) and (input_vout is not None):
        if None not in (input_txid, input_vout):
            input_tx = provider.getrawtransaction(input_txid, 1)
            inp_output = input_tx["vout"][input_vout]
            inp = MutableTxIn(txid=input_txid, txout=input_vout, script_sig=ScriptSig.empty(), sequence=Sequence.max())
            inputs = [inp]
            input_value = int(input_tx["vout"][input_vout]["value"] * coin)
        elif input_address:
            dec_complete_amount = Decimal(complete_amount / coin)
            input_query = provider.select_inputs(input_address, dec_complete_amount)
            inputs = input_query["utxos"]
            input_value = int(input_query["total"] * coin)
            inp = inputs[0] # check!
        else:
            return None
        
        change_value = input_value - complete_amount
        print("Change value and complete amount:", change_value, complete_amount)
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
            change_output = create_p2pkh_txout(change_value, change_address, len(outputs)) # this just gives the correct one
            outputs.append(change_output)
        elif change_value < 0:
            raise Exception("Not enough funds in the input transaction.")

        unsigned_tx = make_raw_transaction(network=network.shortname,
                                       inputs=inputs,
                                       outputs=outputs,
                                       locktime=Locktime(locktime)
                                       )

        return unsigned_tx

    except IndexError: # (IndexError, AttributeError, ValueError):
        raise InvalidTrackedTransactionError("Invalid Transaction creation.")
   


