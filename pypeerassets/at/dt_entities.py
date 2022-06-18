#!/usr/bin/env python

"""Basic classes for coin transactions in DT tokens.
Note: All coin amounts are expressed in Bitcoin satoshi, not in "coins" (using the "from_unit" in networks)
This means that the satoshi amounts do not correspond to the minimum unit in currencies like SLM or PPC with less decimal places."""

from btcpy.structs.script import AbsoluteTimelockScript, P2pkhScript, P2shScript
from btcpy.structs.address import Address, P2shAddress, P2pkhAddress
from btcpy.structs.crypto import PublicKey

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.at.ttx_base import BaseTrackedTransaction, InvalidTrackedTransactionError
from pypeerassets.networks import net_query
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, DONATION_FORMAT, LOCKING_FORMAT, VOTING_FORMAT


# Constants. All TrackedTransactions must follow this scheme of outputs.

P2TH_OUTPUT=0 # output which goes to P2TH address
DATASTR_OUTPUT=1 # output with data string (OP_RETURN)
DONATION_OUTPUT=2 # output with donation/signalling amount
RESERVED_OUTPUT=3 # output for a reservation for other rounds.

class TrackedTransaction(BaseTrackedTransaction):
    """A TrackedTransaction is a transaction tracked by the AT or DT mechanisms.
       The class provides the basic features to handle and check transaction attributes comfortably.
       Note: TrackedTransactions are immutable. Once created they can't easily be changed.
    """

    def __init__(self, deck, provider=None, txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, blockheight=None, blockhash=None):

        # EXPERIMENTAL: BaseTrackedTransaction: comment out
        # For security, should later perhaps be replaced by Transaction.__init__()
        # The difference is that here we don't use self.txid, which results in a (relatively expensive) hashing operation.
        # TODO: recheck MODIFICATIONS during cleanup:
        # datastr is now always taken from self.outs.
        # tx_type trashed, is always set according to type.
        # txjson, does not be needed due to the from_json constructor.
        # epoch, is calculated later from deck value.
        # deck: is made mandatory (can however be None).
        # p2th_address/wif and proposal: trashed (proposal_txid is enough)
        # blockheight -> setting it when creating the obj may be one database op less, so kept for future extensions.
        # TODO: provider could be mandatory
        # TODO: "deck" may not be needed to be stored.
        BaseTrackedTransaction.__init__(self, deck, provider=provider, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, blockheight=blockheight, blockhash=blockhash)

        if type(self) == ProposalTransaction:
            tx_type = "proposal"
        elif type(self) == DonationTransaction:
            tx_type = "donation"
        elif type(self) == SignallingTransaction:
            tx_type = "signalling"
        elif type(self) == LockingTransaction:
            tx_type = "locking"
        elif type(self) == VotingTransaction:
            tx_type = "voting"

        object.__setattr__(self, 'ttx_type', tx_type) # ttx_type simplifies the donor_address algo.

        if type(self) != ProposalTransaction:

            # refactored; proposal_txid and proposal no longer arguments.
            proposal_txid = getfmt(self.datastr, DONATION_FORMAT, "prp").hex()
            object.__setattr__(self, 'proposal_txid', proposal_txid)


        object.__setattr__(self, 'deck', deck)

        # We have to ensure that the deck object is identic for all transactions of the deck (not a copy),
        # so P2TH address is stored.

        epoch = self.blockheight // self.deck.epoch_length if deck is not None else None

        object.__setattr__(self, 'epoch', epoch) # Epoch in which the transaction was sent. Epochs begin with 0.


    def get_output_tx(self, tx_list, proposal_state, dist_round, mode: str=None, debug: bool=False):
        # Searches a locking/donation transaction which shares the address of a signalling or reserve transaction
        # Locking mode searches for the DonationTransaction following to a LockingTransaction.
        # If locking mode, then a reserve address is ignored even if it exists.
        # NOTE: This finds only the first transaction of those searched.

        phase = dist_round // 4
        reserve = False
        direct_successors, indirect_successors = [], []

        try:

            assert mode != "locking"
            addr = self.reserve_address
            tx_type = tx.ttx_type

        except (AttributeError, AssertionError):

            # Here we separate ReserveTXes and SignallingTXes:
            # AttributeError is thrown for SignallingTXes
            # AssertionError for LockingTxes or DonationTxes which act as ReserveTxes

            addr = self.address
            if mode != "locking":
                reserve = True

        # MODIFIED. This list had no proper sorting, so it could led to inconsistent behaviour.
        for tx in sorted(tx_list, key=lambda x: (x.blockheight, x.blockseq)):
            if not proposal_state.check_donor_address(tx, dist_round, addr, reserve=reserve, debug=debug):
                if debug: print("Donor address rejected, already used:", addr)
                continue

            if debug: print("Input addresses of tx", tx.txid, ":", tx.input_addresses)
            # first priority has the direct successor
            if self.txid in [t.txid for t in tx.ins]:
                if debug: print("Added direct successor:", tx.txid)
                direct_successors.append(tx)

            # second priority is the first one of the list which is matching.
            # TODO: It may be needed that first ALL txes are checked for direct successors, then for indirect ones.
            # This would need a rewrite, as then get_output_tx would have to be called twice per tx.
            elif addr in tx.input_addresses:
                if debug: print("Added indirect successor:", tx.txid)
                indirect_successors.append(tx)

        for tx in direct_successors + indirect_successors:
            # in locking mode, we check the block height of the donation release transaction.
            # print("Checking tx", tx)
            if mode == "locking":
                startblock = proposal_state.release_period[0]
                endblock = proposal_state.release_period[1]

            else:
                startblock = proposal_state.rounds[dist_round][1][0]
                endblock = proposal_state.rounds[dist_round][1][1] # last valid block

            if not (startblock <= tx.blockheight <= endblock):
                continue

            proposal_state.add_donor_address(addr, tx.ttx_type, phase, reserve=reserve)
            return tx

        if debug: print("Nothing found.")
        return None

    def get_direct_successors(self, tx_list):
        """all TrackedTransactions of a list which have one of the outputs of the current tx as input."""

        successors = []
        for tx in tx_list:
            if self.txid in [t.txid for t in tx.ins]:
                successors.append(tx)
        return successors

    def get_indirect_successors(self, tx_list, reserve_mode=False):
        """all TrackedTransactions of a list, where one output address is used as one of the input addresses."""

        successors = []
        address = self.reserve_address if reserve_mode else self.address

        for tx in tx_list:
            if address in tx.input_addresses:
                successors.append(tx)
        return successors

    def set_direct_successor(self, tx_list: list, reserve_mode: bool=False):
        # the direct successor is a Locking/Donation transaction that spends the input 2.
        (output, attribute) = (3, "reserve_successor") if reserve_mode else (2, "direct_successor")
        for tx in tx_list:
            if (self.txid == tx.ins[0].txid) and (tx.ins[0].txout == output):
                object.__setattr__(self, attribute, tx)
                break


class LockingTransaction(TrackedTransaction):
    """A LockingTransaction is a transaction which locks the donation amount until the end of the
       working period of the Proposer. They are only necessary in the first phase (round 1-4)."""

    def __init__(self, deck, txid=None, timelock=None, d_address=None, d_amount=None, reserved_amount=None, reserve_address=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, p2sh_address=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        if len(outs) > 0:
            # CONVENTION: Donation is in output 2 (0: P2TH, 1: OP_RETURN).
            # Reserved amount, if existing, is in output 3.
            locked_out = outs[DONATION_OUTPUT]

            if not d_amount:
                d_amount = locked_out.value # amount in satoshi

            try:
                p2sh_script = locked_out.script_pubkey
                #print("TX P2SH script", p2sh_script)
                fmt = LOCKING_FORMAT
                public_timelock = int.from_bytes(getfmt(self.datastr, fmt, "lck"), "big")
                public_dest_address = getfmt(self.datastr, fmt, "adr").decode("utf-8") # this is the address of the pubkey needed to unlock
                redeem_script = DonationTimeLockScript(raw_locktime=public_timelock, dest_address_string=public_dest_address, network=network)
                redeem_script_p2sh = P2shScript(redeem_script)

                #print("Destination address:", public_dest_address)
                #print("Redeem script:", redeem_script)
                #print("Redeem script P2SH:", redeem_script_p2sh)
                p2sh_address = P2shAddress.from_script(redeem_script, network=network)
                #print("P2SH address:", p2sh_address)


                if not redeem_script_p2sh == p2sh_script:
                    raise InvalidTrackedTransactionError("Incorrect Locktime and address data.")

                else:
                    timelock = public_timelock
                    d_address = public_dest_address

                if not p2sh_address:
                    p2sh_address = P2shAddress.from_script(p2sh_script, network=network)

            except AttributeError:
                raise InvalidTrackedTransactionError("Incorrectly formatted LockingTransaction.")

            if len(outs) > 3 and not reserved_amount:

                reserved_out = outs[RESERVED_OUTPUT]
                reserved_amount = reserved_out.value
                reserve_address = reserved_out.script_pubkey.address(network=network).__str__()

        object.__setattr__(self, 'timelock', timelock)
        object.__setattr__(self, 'address', d_address) # address to unlock the redeem script
        object.__setattr__(self, 'amount', d_amount) # donation amount
        object.__setattr__(self, 'p2sh_address', p2sh_address) # P2SH address generated by CLTV script
        object.__setattr__(self, 'redeem_script', redeem_script)

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.

class DonationTransaction(TrackedTransaction):
    """A DonationTransaction is a transaction which transfers the donation to the Proposer."""

    def __init__(self, deck, txid=None, d_address=None, d_amount=None, reserved_amount=None, reserve_address=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        try:
            if len(outs) > 0:
                donation_out = outs[DONATION_OUTPUT]

                if not d_amount:
                    d_amount = donation_out.value # amount in satoshi
                if not d_address:
                    d_address = donation_out.script_pubkey.address(network=network).__str__()

            if len(outs) > 3 and not reserved_amount: # we need this for round 5.

                reserved_out = outs[RESERVED_OUTPUT]
                reserved_amount = reserved_out.value
                reserve_address = reserved_out.script_pubkey.address(network=network).__str__()


        except AttributeError:
                raise InvalidTrackedTransactionError("Incorrectly formatted DonationTransaction.")

        object.__setattr__(self, 'address', d_address) # donation address: the address defined in the referenced Proposal
        object.__setattr__(self, 'amount', d_amount) # donation amount

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.


class SignallingTransaction(TrackedTransaction):
    """A SignallingTransaction is a transaction where a Potential Donor signals available funds."""

    def __init__(self, deck, txid=None, s_amount=None, s_address=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockhash=None, blockheight=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        if outs:
            # CONVENTION: Signalling is in output 2 (0: P2TH, 1: OP_RETURN).
            signalling_out = outs[2]
            if not s_address:
                s_address = signalling_out.script_pubkey.address(network=network).__str__()
            if not s_amount:
                s_amount = signalling_out.value # note: amount is in satoshi

        object.__setattr__(self, 'amount', s_amount)

        # address: the "project specific donation address".
        # To preserve privileges in the later rounds it has to be always the same one.
        object.__setattr__(self, 'address', s_address)


class ProposalTransaction(TrackedTransaction):
    """A ProposalTransaction is the transaction where a DT Proposer (originator) specifies required amount and donation address."""
    # Modified: instead of previous_proposal, we use first_ptx_txid. We always reference the first tx, not a previous modification.

    def __init__(self, deck, txid=None, donation_address=None, epoch_number=None, round_length=None, req_amount=None, first_ptx_txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockhash=None, blockheight=None):


        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        fmt = PROPOSAL_FORMAT

        # this deck_id storage is redundant. It is however perhaps better to do this here.
        # deck_id = getfmt(self.datastr, fmt, "dck").hex() # MODIFIED to hex. check if it does harm.

        epoch_number = int.from_bytes(getfmt(self.datastr, fmt, "eps"), "big")
        round_length = int.from_bytes(getfmt(self.datastr, fmt, "sla"), "big")
        req_amount = int.from_bytes(getfmt(self.datastr, fmt, "amt"), "big") * self.coin_multiplier()

        if len(self.datastr) > fmt["ptx"][0] and not first_ptx_txid:
            first_ptx_txid_raw = getfmt(self.datastr, fmt, "ptx")
            # TODO: the following should be uncommented once this testing round is ready, as this check makes sense.
            #if len(first_ptx_txid_raw) != 32:
            #     raise InvalidTrackedTransactionError("TXID of first transaction is in wrong format.")

        # Donation Address. This one must be one from which the ProposalTransaction was signed.
        # Otherwise spammers could confuse the system.
        # CONVENTION for now: It is the address of the FIRST input of the ProposalTransaction.
        if not donation_address:
            try:
                input_txid = self.ins[0].txid
                input_vout = self.ins[0].txout
                input_tx = provider.getrawtransaction(input_txid, 1)
                donation_address = input_tx["vout"][input_vout]["scriptPubKey"]["addresses"][0]

            except (KeyError, IndexError) as e:
                print(e)
                raise InvalidTrackedTransactionError("Proposal transaction has no valid donation address.")

        object.__setattr__(self, 'donation_address', donation_address)

        object.__setattr__(self, 'epoch_number', epoch_number) # epochs: epochs to work on.
        object.__setattr__(self, 'round_length', round_length) # Proposer can define length of each round of the distribution.
        object.__setattr__(self, 'req_amount', req_amount) # Requested amount of coin units.
        object.__setattr__(self, 'first_ptx_txid', first_ptx_txid_raw.hex()) # TXID of the first ProposalTransaction of a ProposalState (in case there are more than one).

class VotingTransaction(TrackedTransaction):
    # very simple custom protocol, because the original PeerAssets voting protocol has two problems:
    # 1. it requires an extra transaction to be sent (which would have to be sent by the Proposer => more fees)
    # 2. it requires too many addresses to be generated and imported into the client (1 per vote option).
    # This one only requires one P2TH output and a (relatively small) OP_RETURN output per voting transaction.
    # For the vote value, we use b'+' and b'-', so the vote can be seen in the datastring.
    # TODO: Implement that a vote in start epoch is not needed to be repeated in end epoch.
    # This need some additional considerations: what if a start epoch voter sells his tokens before end epoch?
    # So it would need to update the vote by the balance in round 2? This would be perhaps even better.

    # Vote is always cast with the entire current balance.

    def __init__(self, deck, txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, vote=None, sender=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        if not vote:
            vote = getfmt(self.datastr, VOTING_FORMAT, "vot")
        object.__setattr__(self, "vote", vote)

        if not sender:
            input_tx = self.ins[0].txid
            input_vout = self.ins[0].txout
            sender = provider.getrawtransaction(input_tx, 1)["vout"][input_vout]["scriptPubKey"]["addresses"][0]


        object.__setattr__(self, "sender", sender)

    def set_weight(self, weight):
        object.__setattr__(self, "vote_weight", weight) # TODO: why does "vote_weight" work, but "weight" doesn't???

# Scripts for Timelock contract
# we can use the verify function to extract the locktime from the script.
# Script (with opcodes) -> bytes: compile function
# bytes -> Script: decompile

class DonationTimeLockScript(AbsoluteTimelockScript):

    def __init__(self, raw_locktime, dest_address_string, network=None):
        """
        :param args: if one arg is provided it is interpreted as a script, which is in turn
        verified and `locktime` and `locked_script` are extracted. If two args are provided,
        they are interpreted as `locktime` and `locked_script` respectively, the script is
        then generated from these params
        """
        dest_address = Address.from_string(dest_address_string, network=network)
        locktime = Locktime(raw_locktime)
        locked_script = P2pkhScript(dest_address)
        super().__init__(locktime, locked_script)

