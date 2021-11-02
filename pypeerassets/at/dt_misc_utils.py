from pypeerassets.at.dt_entities import ProposalTransaction, DonationTimeLockScript
from pypeerassets.at.dt_states import ProposalState
from pypeerassets.at.dt_parser import ParserState, dt_parser
from pypeerassets.at.dt_parser_utils import deck_from_tx
from pypeerassets.__main__ import get_card_bundles
from pypeerassets.provider import Provider
from pypeerassets.protocol import Deck
from pypeerassets.kutil import Kutil
from pypeerassets.transactions import make_raw_transaction, p2pkh_script, find_parent_outputs, nulldata_script, MutableTxIn, TxIn, TxOut, Transaction, MutableTransaction, MutableTxIn, ScriptSig, Locktime
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, net_query
from pypeerassets.provider.rpcnode import Sequence
from btcpy.structs.address import P2shAddress
from btcpy.structs.script import P2shScript, AbsoluteTimelockScript
from btcpy.structs.sig import P2shSolver, AbsoluteTimelockSolver, P2pkhSolver
from decimal import Decimal
from pypeerassets.at.dt_entities import InvalidTrackedTransactionError
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT
from pypeerassets.legacy import is_legacy_blockchain
from collections import namedtuple

## Basic functions

def coin_value(network_name: str=None, network: namedtuple=None):
    if network is None:
        if network_name is None:
            raise ValueError("You must provide either network name or network object.")
        else:
            network = net_query(network_name)

    return int(1 / network.from_unit)

def sats_to_coins(sats: int, network_name: str=None, network: namedtuple=None) -> Decimal:
    return Decimal(sats) / coin_value(network_name, network)

def coins_to_sats(coins: Decimal, network_name: str=None, network: namedtuple=None) -> int:
    return int(coins * coin_value(network_name, network))

def min_p2th_fee(network) -> int:
    # normally, the minimal tx fee in PPC and derived coins is the same than the minimal amount for an output.
    # the correct way however may be:
    # txout = network.tx_cls_out()
    # return txout.get_dust_threshold()
    return network.min_tx_fee

## States / Periods

def get_votestate(provider, proposal_txid, debug=False):
    """Get the state of the votes of a Proposal without calling the parser completely."""

    proposal = get_proposal_state(provider, proposal_txid, debug=debug) # Modified: eliminated phase=1 parameter.
    decimals = proposal.deck.number_of_decimals
    # We use the main deck's decimals as a base, and adjust its weight in the parser according to the
    # difference in number of decimals between main deck and SDP deck.

    result = []
    for phase_votes in (proposal.initial_votes, proposal.final_votes):
        try:
            result.append(format_votes(decimals, phase_votes))
        except TypeError: # gets thrown if votes of a phase aren't available yet
            pass
    return result

def get_dstates_from_txid(txid: str, proposal_state: ProposalState, only_signalling=False):
    # returns donation state from a signalling, locking or donation transaction.
    # If the tx given includes a reserved amount; then it will be shown in two dstates, and both being returned.
    # The only_signalling flag avoids that a txid gives two results (necessary for pacli's get_previous_tx_input_data).
    # It only searches in txes marked as signalling and reserve transactions, which are the ones needed for this function;
    # if allowing the other tx types, there could be a donation/locking tx as well.

    allowed_txes = [ds.signalling_tx.txid, ds.reserve_tx.txid]
    if not only_signalling:
        allowed_txes += [ds.locking_tx.txid, ds.donation_tx.txid]
    result = []
    for ds in proposal_state.donation_states:
        if txid in allowed_txes:
            result.append(ds)
    else:
        return None

    return result


def get_dstates_from_address(address: str, proposal_state: ProposalState, dist_round: int=None):
    # returns donation state from a signalling, locking or donation transaction.
    # Uses the destination address, which is the address from which the donor will do locking/donation.

    states = []
    # print("Donation states:", proposal_state.donation_states)
    for rd, rd_states in enumerate(proposal_state.donation_states):


        if dist_round and (rd != dist_round):
            continue

        for ds in rd_states.values():
            for tx in [ ds.signalling_tx, ds.locking_tx, ds.reserve_tx ]:
               if tx is None:
                   continue
               try:
                   tx_addr = tx.reserve_address.__str__()
               except AttributeError: # SignallingTX
                   tx_addr = tx.address.__str__()
                   # print(tx_addr, address)
               if tx_addr == address:
                   states.append(ds)

    return states

def get_donation_states(provider, proposal_id=None, proposal_tx=None, tx_txid=None, address=None, phase=1, debug=False, dist_round=None, pos=None):

    # NOTE: phase is set as a default to 1.
    # NOTE: we give the option to call this function already with the full proposal_tx if already available.
    proposal_state = get_proposal_state(provider, proposal_id=proposal_id, proposal_tx=proposal_tx, debug=debug)

    if tx_txid is not None:
        # MODIFIED: gives now a list, because it can have two results if the tx includes a reserved amount.
        # result = get_dstate_from_txid(txid, proposal_state)
        result = get_dstates_from_txid(tx_txid, proposal_state)
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
        result = [s for rddict in proposal_state.donation_states for s in rddict.values()]

    return result

def proposal_from_tx(proposal_id, provider):
    basicdata = ProposalTransaction.get_basicdata(proposal_id, provider)
    deckid = getfmt(basicdata["data"], PROPOSAL_FORMAT, "dck").hex()
    deck = deck_from_tx(deckid, provider)
    return ProposalTransaction.from_txid(proposal_id, provider, deck=deck, basicdata=basicdata)


def get_parser_state(provider, deck=None, deckid=None, lastblock=None, debug=False, force_continue=False, force_dstates=False):

    if not deck:
        if not deckid:
            raise ValueError("No deck id provided.")
        deck = deck_from_tx(deckid, provider)

    unfiltered_cards = list((card for batch in get_card_bundles(provider, deck) for card in batch))

    pst = ParserState(deck, unfiltered_cards, provider, current_blockheight=lastblock, debug=debug)

    valid_cards = dt_parser(unfiltered_cards, provider, deck, current_blockheight=lastblock, debug=debug, initial_parser_state=pst, force_continue=force_continue, force_dstates=force_dstates) # later add: force_dstates=True

    # NOTE: we don't need to return valid_cards as it is saved in pst.
    return pst

def get_proposal_state(provider, proposal_id=None, proposal_tx=None, debug=False, deck=None):
    # version 2: does not create an additional proposal state and always does the complete check (phase=1).
    # MODIFIED: parameter phase eliminated. If we needed it, we could also derive it from the ptx values.

    current_blockheight = provider.getblockcount()
    if not proposal_tx:
        ptx = proposal_from_tx(proposal_id, provider)
    else:
        ptx = proposal_tx
        proposal_id = ptx.txid

    # pstate = ProposalState(first_ptx=ptx, valid_ptx=ptx, provider=provider)
    if debug: print("Deck:", ptx.deck.id)

    #if phase == 0:
    #    lastblock = min(current_blockheight, pstate.dist_start + pstate.deck.epoch_length)
    #elif phase == 1:
    #    lastblock = min(current_blockheight, (pstate.end_epoch + 1) * pstate.deck.epoch_length)
    #else:
    #    raise ValueError("No correct phase number entered. Please enter 0 or 1.")

    pst = get_parser_state(provider, deck=ptx.deck, lastblock=current_blockheight, debug=debug, force_continue=True, force_dstates=True)

    for p in pst.proposal_states.values():
        if debug: print("Checking proposal:", p.id)
        if p.id == proposal_id:
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

def create_p2pkh_txout(value: int, address: str, n: int, network: namedtuple):
    #address = Address.from_string(addr_string)
    #script = P2pkhScript(address)
    script = p2pkh_script(network.shortname, address) # we need the shortname here
    return TxOut(value=value, n=n, script_pubkey=script, network=network)

def create_p2sh_txout(value: int, redeem_script: DonationTimeLockScript, n: int, network: namedtuple):
    p2sh_script = P2shScript(redeem_script)
    out = TxOut(value=value, n=n, script_pubkey=p2sh_script, network=network)
    #print("=========== P2SH TEST ============")
    #print("P2SH output:", out)
    #print("P2SH output pubkey:", out.script_pubkey)
    #print("P2SH script:", p2sh_script)
    #print("Redeem script:", redeem_script)
    return out

def create_redeem_script(address: str, timelock: int, network: namedtuple):
    return DonationTimeLockScript(raw_locktime=timelock, dest_address_string=address, network=network)

def create_p2sh_address(redeem_script: DonationTimeLockScript, network: namedtuple):
    return P2shAddress.from_script(redeem_script, network=network)

def create_p2th_txout(deck, tx_type, fee, network: namedtuple):
    # Warning: always creates the p2th out at n=0.
    p2th_addr = deck.derived_p2th_address(tx_type)
    return create_p2pkh_txout(value=fee, address=p2th_addr, n=0, network=network)

def create_opreturn_txout(tx_type: str, data: bytes, network: namedtuple, position=1):
    # By default creates the opreturn out at n=1.
    # MODIFIED: if the blockchain doesn't support 0 values, then a min_tx_fee value is created.
    script = nulldata_script(data)
    if is_legacy_blockchain(network.shortname, "nulldata"):
        value = coins_to_sats(network.min_tx_fee, network.shortname, network)
    else:
        value = 0
    return TxOut(value=value, n=position, script_pubkey=script, network=network)


def create_unsigned_tx(deck: Deck, provider: Provider, tx_type: str, network_name: str, amount: int=None, proposal_txid: str=None, data: bytes=None, address: str=None, version: int=1, change_address: str=None, tx_fee: int=None, p2th_fee: int=None, input_txid: str=None, input_vout: int=None, input_address: str=None, locktime: int=0, cltv_timelock: int=0, reserved_amount: int=None, reserve_address: str=None, debug: bool=False):

    if tx_type != "proposal":
        if data and (not proposal_txid):
            proposal_txid = str(data[2:34].hex())

    try:
        network = net_query(network_name)
        if not tx_fee:
            # We use a flat fee, as tx will be mostly under 1 kB (check would be complicated). If it's bigger, an error will be thrown.
            # In coins without min_tx_fee, the fee must be set manually.
            if network.min_tx_fee > 0:
                tx_fee = coins_to_sats(network.min_tx_fee, network=network)
            else:
                raise ValueError("This coin has no minimum transaction fee. You must provide the fee manually.")
        if not p2th_fee:
            p2th_fee = coins_to_sats(min_p2th_fee(network), network=network)

        p2th_output = create_p2th_txout(deck, tx_type, fee=p2th_fee, network=network)
        data_output = create_opreturn_txout(tx_type, data, network=network)

        if (address == None) and (tx_type == "donation"):
            ptx = proposal_from_tx(proposal_txid, provider)
            address = ptx.donation_address

        outputs = [p2th_output, data_output]
        if tx_type == "locking":
            # First create redeem script, then P2SH address, then the output spending to that script.
            redeem_script = create_redeem_script(address=address, timelock=cltv_timelock, network=network)
            p2sh_script = P2shScript(redeem_script)
            p2sh_addr = create_p2sh_address(redeem_script, network=network)
            if debug: print("Timelock", cltv_timelock)
            if debug: print("Redeem script", redeem_script)
            if debug: print("P2SH script", p2sh_script)
            print("P2SH address generated by this Locking Transaction:", p2sh_addr)
            print("You will need the keys for address", address, "to spend funds.")
            p2sh_output = create_p2sh_txout(amount, redeem_script, n=2, network=network)
            outputs.append(p2sh_output)
        elif tx_type in ("signalling", "donation"):
            value_output = create_p2pkh_txout(value=amount, address=address, n=2, network=network)
            outputs.append(value_output)
        else:
            amount = 0 # proposal and vote types do not have amount.

        if reserved_amount is not None:
            outputs.append(create_p2pkh_txout(reserved_amount, reserve_address, 3, network=network))
        else:
            reserved_amount = 0

        complete_amount = amount + reserved_amount + p2th_output.value + data_output.value + tx_fee

        if None not in (input_txid, input_vout):
            input_tx = provider.getrawtransaction(input_txid, 1)
            inp_output = input_tx["vout"][input_vout]
            inp = MutableTxIn(txid=input_txid, txout=input_vout, script_sig=ScriptSig.empty(), sequence=Sequence.max())
            inputs = [inp]
            input_value = coins_to_sats(Decimal(input_tx["vout"][input_vout]["value"]), network=network)
        elif input_address:
            dec_complete_amount = sats_to_coins(Decimal(complete_amount), network=network)
            input_query = provider.select_inputs(input_address, dec_complete_amount)
            inputs = input_query["utxos"]
            input_value = coins_to_sats(Decimal(input_query["total"]), network=network)
        else:
            raise ValueError("No input information provided.") # we need input address or input txid/vout

        change_value = input_value - complete_amount
        if debug: print("Change value and complete amount:", change_value, complete_amount)

        # Look if there is change, if yes, create fourth output.
        if change_value >= p2th_fee: # Change amount must be higher then the minimum amount, which is equal to the default p2th_fee. Otherwise it will be discarded as fee.
            # If no change address is delivered we use the address from the input.
            if change_address is None:
                if input_address is None:
                    change_address = inp_output['scriptPubKey']['addresses'][0]
                else:
                    change_address = input_address
            change_output = create_p2pkh_txout(change_value, change_address, len(outputs), network) # this just gives the correct one
            outputs.append(change_output)
        elif change_value < 0:
            raise Exception("Not enough funds in the input transaction.")

        unsigned_tx = make_raw_transaction(network=network.shortname,
                                       inputs=inputs,
                                       outputs=outputs,
                                       locktime=Locktime(locktime)
                                       )

        if (unsigned_tx.size > 1000) and (network.min_tx_fee > 0):
            # For now we don't change the fee/change value if the size is higher as 1 kB. May change in future versions.
            raise Exception("Transaction too big (max: 1 kB). Please use other inputs or another address.")
        return unsigned_tx

    except IndexError: # (IndexError, AttributeError, ValueError):
        raise InvalidTrackedTransactionError("Invalid Transaction creation.")


def sign_p2sh_transaction(provider: Provider, unsigned: MutableTransaction, redeem_script: AbsoluteTimelockScript, key: Kutil):

    # Original for P2PKH uses Kutil.
    # from pypeerassets kutil:
    # "due to design of the btcpy library, TxIn object must be converted to TxOut object before signing"
    txins = [find_parent_outputs(provider, i) for i in unsigned.ins]
    inner_solver = P2pkhSolver(key._private_key)

    solver = AbsoluteTimelockSolver(redeem_script.locktime, inner_solver) # TODO: re-check if this is confirmed and works as expected.
    # redeem_script_solver = AbsoluteTimelockSolver(redeem_script.locktime, inner_solver)
    # solver = P2shSolver(redeem_script, redeem_script_solver)
    #print(txins)
    #print(inner_solver)
    #print(solver)

    return unsigned.spend(txins, [solver for i in txins])
