#!/usr/bin/env python

"""Basic classes for coin transactions in DT tokens.
Note: All coin amounts are expressed in Bitcoin satoshi, not in "coins" (using the "from_unit" in networks)
This means that the satoshi amounts do not correspond to the minimum unit in currencies like SLM or PPC with less decimal places.""" # TODO this is probably obsolete

from btcpy.structs.script import AbsoluteTimelockScript, P2pkhScript, P2shScript
from btcpy.structs.address import Address, P2shAddress, P2pkhAddress
from btcpy.structs.crypto import PublicKey

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.at.ttx_base import BaseTrackedTransaction, InvalidTrackedTransactionError
from pypeerassets.networks import net_query
from pypeerassets.hash_encoding import hash_to_address
from pypeerassets.at.constants import P2TH_OUTPUT, DATASTR_OUTPUT, DONATION_OUTPUT, RESERVED_OUTPUT


class TrackedTransaction(BaseTrackedTransaction):
    """A TrackedTransaction is a transaction tracked by the AT or DT mechanisms.
       The class provides the basic features to handle and check transaction attributes comfortably.
       Note: TrackedTransactions are immutable. Once created they can't easily be changed.
    """

    def __init__(self, deck, provider=None, txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, blockheight=None, blockhash=None):

        # For security, should later perhaps be replaced by Transaction.__init__()
        # The difference is that here we don't use self.txid, which results in a (relatively expensive) hashing operation.
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
            proposal_txid = self.metadata["txid"].hex()
            object.__setattr__(self, 'proposal_txid', proposal_txid)

        object.__setattr__(self, 'deck', deck)

        # We have to ensure that the deck object is identic for all transactions of the deck (not a copy),
        # so P2TH address is stored.

        epoch = self.blockheight // self.deck.epoch_length if deck is not None else None
        object.__setattr__(self, 'epoch', epoch) # Epoch in which the transaction was sent. Epochs begin with 0.

    def get_direct_successors(self, tx_list):
        """all TrackedTransactions of a list which have one of the outputs of the current tx as input."""

        successors = []
        for tx in tx_list:
            if self.txid in [t.txid for t in tx.ins]:
                successors.append(tx)
        return successors

    def get_indirect_successors(self, tx_list: list, reserve_mode: bool=False):
        """all TrackedTransactions of a list, where one output address is used as one of the input addresses."""
        # This has to be called always _after_ set_dist_round/validate_round.

        successors = []
        address = self.reserve_address if reserve_mode else self.address

        for tx in tx_list:
            # MODIF: we don't search in all input_addresses but compare to the specific donor address.
            # DonationTransactions which don't have direct predecessors and thus no donor_address, get the donor_address set
            if (type(tx) == DonationTransaction) and (tx.donor_address is None):
                tx.set_donor_address(dist_round=self.dist_round)
            #if address in tx.input_addresses:
            if address == tx.donor_address:
                successors.append(tx)
        return successors

    def set_direct_successor(self, tx_list: list, reserve_mode: bool=False):
        # the direct successor is a Locking/Donation transaction that spends the input 2.
        # MODIF: returned True or False according to if a successor was added or not

        (output, attribute) = (3, "reserve_successor") if reserve_mode else (2, "direct_successor")
        for tx in tx_list:
            if (self.txid == tx.ins[0].txid) and (tx.ins[0].txout == output):
                object.__setattr__(self, attribute, tx)
                return True
        else:
            return False

    def set_dist_round(self, dist_round: int):
        # MODIF: setting the dist round for all tracked transactions has some advantages.)
        object.__setattr__(self, 'dist_round', dist_round)


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
                public_timelock = self.metadata["locktime"]
                try:
                    lockhash_type = self.metadata["lockhash_type"]
                    public_dest_address = hash_to_address(self.metadata["lockhash"], lockhash_type, network)
                except (ValueError, NotImplementedError):
                    raise InvalidTrackedTransactionError("Unsupported hash type.")

                redeem_script = DonationTimeLockScript(raw_locktime=public_timelock, dest_address_string=public_dest_address, network=network)
                redeem_script_p2sh = P2shScript(redeem_script)
                p2sh_address = P2shAddress.from_script(redeem_script, network=network)

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
        object.__setattr__(self, 'lockhash_type', lockhash_type)
        object.__setattr__(self, 'amount', d_amount) # donation amount
        object.__setattr__(self, 'p2sh_address', p2sh_address) # P2SH address generated by CLTV script
        object.__setattr__(self, 'redeem_script', redeem_script)
        # In LockingTransactions the donor address is the first input address.
        object.__setattr__(self, 'donor_address', self.input_addresses[0])

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

        # Destination address. This has to be the address defined in the referenced Proposal
        object.__setattr__(self, 'address', d_address)
        object.__setattr__(self, 'amount', d_amount) # donation amount
        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.

    def set_donor_address(self, dist_round: int=None, direct_predecessor: LockingTransaction=None):
        # In direct donation txes, the donor_address is the first input sender.
        # If the address is direct successor of a LockingTransaction, the
        # donor address is the donor address of the LockingTransaction.
        # If not, then it's the first input sender.
        # This implements the following rule correctly and without ambiguities:
        # If you use new inputs, you MUST sign the DonationTransaction
        # with your donor address. If you use the locked funds,
        # it can be another address.
        if direct_predecessor is not None:
            donor_address = direct_predecessor.donor_address
        elif dist_round >= 4:
            donor_address = self.input_addresses[0]
        else:
            raise ValueError("Incorrect round.")

        object.__setattr__(self, 'donor_address', donor_address)


class SignallingTransaction(TrackedTransaction):
    """A SignallingTransaction is a transaction where a Potential Donor signals available funds.
    Per convention, the signalled funds are in output 2 of the transaction."""

    def __init__(self, deck, txid=None, s_amount=None, s_address=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockhash=None, blockheight=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        if outs:
            signalling_out = outs[2]
            if not s_address:
                s_address = signalling_out.script_pubkey.address(network=network).__str__()
            if not s_amount:
                s_amount = signalling_out.value # note: amount is in satoshi

        object.__setattr__(self, 'amount', s_amount)
        # address: the destination address. Maybe obsolete here. (TODO)
        object.__setattr__(self, 'address', s_address)

        # The donor address attribute, in Locking and Signalling transactions,
        # points to the project specific donor address.
        # In SignallingTransactions it's the destination address, while in
        # LockingTransactions it's the tx sender (first input address).
        # To preserve privileges in the later rounds it has to be used
        # as origin address for the signalled/reserved amounts.
        object.__setattr__(self, 'donor_address', s_address)

class ProposalTransaction(TrackedTransaction):
    """A ProposalTransaction is the transaction where a DT Proposer (originator) specifies required amount and donation address.
       By convention, the donation address is the one belonging to the same key who signed the first input of the transaction."""

    def __init__(self, deck, txid=None, donation_address=None, epoch_number=None, round_length=None, req_amount=None, first_ptx_txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockhash=None, blockheight=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        epoch_number = self.metadata["epochs"]
        # NOTE: req_amount was before a small int number, now it can be a number of up to the max amount of decimal places
        req_amount = self.metadata["amount"]
        # Description. Short optional string which can be used to describe or give a name (non-unique) to the Proposal.
        description = self.metadata.get("description")

        if first_ptx_txid is None:
            if "txid" in self.metadata and type(self.metadata["txid"]) == bytes:
                try:
                    first_ptx_txid = self.metadata["txid"].hex()
                    assert len(first_ptx_txid) == 64 # 64 because the hex conversion is before
                except AssertionError:
                    raise InvalidTrackedTransactionError("TXID of modified proposal is in wrong format.")

        # even if importing complete pautils module.
        if not donation_address:
            try:
                # donation_address = pu.find_tx_sender(self.to_json)
                input_txid = self.ins[0].txid
                input_vout = self.ins[0].txout
                input_tx = provider.getrawtransaction(input_txid, 1)
                donation_address = input_tx["vout"][input_vout]["scriptPubKey"]["addresses"][0]

            except (KeyError, IndexError) as e:
                print(e)
                raise InvalidTrackedTransactionError("Proposal transaction has no valid donation address.")

        object.__setattr__(self, 'donation_address', donation_address)
        object.__setattr__(self, 'epoch_number', epoch_number) # epochs: epochs to work on.
        object.__setattr__(self, 'description', description) # Requested amount of coin units.
        object.__setattr__(self, 'req_amount', req_amount) # Requested amount of coin units.
        object.__setattr__(self, 'first_ptx_txid', first_ptx_txid)

class VotingTransaction(TrackedTransaction):
    """Very simple custom protocol, because the original PeerAssets voting protocol has two problems:
    # 1. it requires an extra transaction to be sent (which would have to be sent by the Proposer => more fees)
    # 2. it requires too many addresses to be generated and imported into the client (1 per vote option).
    # This one only requires one P2TH output and a (relatively small) OP_RETURN output per voting transaction.
    Vote is always cast with the entire current balance"""

    def __init__(self, deck, txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, vote=None, sender=None):

        TrackedTransaction.__init__(self, deck, txid=txid, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, blockheight=blockheight, blockhash=blockhash)

        if vote is None:
            vote = self.metadata["vote"]
        object.__setattr__(self, "vote", vote)

        if not sender:
            input_tx = self.ins[0].txid
            input_vout = self.ins[0].txout
            sender = provider.getrawtransaction(input_tx, 1)["vout"][input_vout]["scriptPubKey"]["addresses"][0]

        object.__setattr__(self, "sender", sender)

    def set_weight(self, weight):
        # TODO: research strange bug here: "vote_weight" works, but "weight" doesn't
        object.__setattr__(self, "vote_weight", weight)

# Scripts for Timelock contract
# we can use the verify function to extract the locktime from the script.
# Script (with opcodes) -> bytes: compile function
# bytes -> Script: decompile

class DonationTimeLockScript(AbsoluteTimelockScript):

    def __init__(self, raw_locktime, dest_address_string, network):
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

