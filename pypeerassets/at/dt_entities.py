#!/usr/bin/env python

"""Basic classes for coin transactions in DT tokens.
Note: All coin amounts are expressed in Bitcoin satoshi, not in "coins" (using the "from_unit" in networks)
This means that the satoshi amounts do not correspond to the minimum unit in currencies like SLM or PPC with less decimal places."""

from btcpy.structs.script import AbsoluteTimelockScript, Hashlock256Script, IfElseScript, P2pkhScript, P2shScript, ScriptBuilder
from btcpy.structs.address import Address, P2shAddress, P2pkhAddress
from btcpy.structs.crypto import PublicKey

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime, nulldata_script, tx_output, find_parent_outputs, p2pkh_script
from pypeerassets.provider import RpcNode
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, SlimcoinMainnet, SlimcoinTestnet, net_query
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, DONATION_FORMAT, SIGNALLING_FORMAT, LOCKING_FORMAT, VOTING_FORMAT
from pypeerassets.legacy import is_legacy_blockchain
import hashlib as hl


# Constants. All TrackedTransactions must follow this scheme of outputs.

P2TH_OUTPUT=0 # output which goes to P2TH address
DATASTR_OUTPUT=1 # output with data string (OP_RETURN)
DONATION_OUTPUT=2 # output with donation/signalling amount
RESERVED_OUTPUT=3 # output for a reservation for other rounds.

class TrackedTransaction(Transaction):
    """A TrackedTransaction is a transaction tracked by the AT or DT mechanisms.
       The class provides the basic features to handle and check transaction attributes comfortably.
       Note: TrackedTransactions are immutable. Once created they can't easily be changed.
    """

    def __init__(self, tx_type=None, txjson=None, txid=None, proposal=None, p2th_address=None, p2th_wif=None, dist_round=None, version=None, ins=[], outs=[], locktime=0, network=PeercoinTestnet, timestamp=None, provider=None, datastr=None, deck=None, epoch=None, blockheight=None, blockhash=None):

        # For security, should later perhaps be replaced by Transaction.__init__()
        # The difference is that here we don't use self.txid, which results in a (relatively expensive) hashing operation.

        object.__setattr__(self, 'version', version)
        object.__setattr__(self, 'ins', tuple(ins))
        object.__setattr__(self, 'outs', tuple(outs))
        object.__setattr__(self, 'locktime', locktime)
        object.__setattr__(self, '_txid', txid)
        object.__setattr__(self, 'network', network)
        object.__setattr__(self, 'timestamp', timestamp)

        if type(self) == ProposalTransaction:
            tx_type = "proposal"
        elif type(self) == DonationTransaction:
            tx_type = "donation"
        elif type(self) == SignallingTransaction:
            tx_type = "signalling"

        object.__setattr__(self, 'input_addresses', self.set_input_addresses(provider=provider))

        if not blockheight:

            if txid and not blockhash: # blockhash included by from_json constructor
                if not txjson:
                    txjson = provider.getrawtransaction(txid, 1)
                    blockhash = txjson["blockhash"]

            if blockhash:
                try:
                    blockheight = provider.getblock(blockhash, True)["height"]
                except KeyError:
                    blockheight = None # unconfirmed transaction


        object.__setattr__(self, 'blockheight', blockheight)


        # Inputs and outputs must always be provided by constructors.
        if len(ins) == 0 or len(outs) < 3:
            raise InvalidTrackedTransactionError("Creating a TrackedTransaction you must provide inputs and outputs.")

        # other attributes come from datastr
        # CONVENTION: datastr is always in SECOND output (outs[1]) like in PeerAssets tx.

        if not datastr:
            try:
                scriptpubkey = self.outs[DATASTR_OUTPUT].script_pubkey
                datastr = bytes(scriptpubkey.data.data)
            except Exception as e: # if no op_return it throws InvalidNulldataOutput
                raise InvalidTrackedTransactionError("No OP_RETURN data.")

        object.__setattr__(self, 'datastr', datastr) # OP_RETURN data byte string

        if type(self) != ProposalTransaction:
            # refactored; proposal_txid no longer an argument.
            if proposal:
                proposal_txid = proposal.txid
                if not deck:
                   deck = proposal.deck
            else:
                proposal_txid = getfmt(self.datastr, DONATION_FORMAT, "prp").hex()

            object.__setattr__(self, 'proposal_txid', proposal_txid)
            # TODO: it's maybe not necessary to store the whole proposal object here!
            object.__setattr__(self, 'proposal', proposal)
            # dist_round: in case of Signalling or Donation TXes, the round when they were sent.
            object.__setattr__(self, 'dist_round', dist_round)

        object.__setattr__(self, 'deck', deck)
        # We have to ensure that the deck object is identic for all transactions of the deck (not a copy),
        # so P2TH address is stored.

        if deck:
            if not p2th_address:
                p2th_address = self.deck.derived_p2th_address(tx_type)

            # This seems to be notably slower than P2TH_address
            # Probably we need it only for Bitcoin-0.6 based code
            if is_legacy_blockchain(network.shortname) and (p2th_wif is None):
                p2th_wif = self.deck.derived_p2th_wif(tx_type)

            epoch = self.blockheight // self.deck.epoch_length

        object.__setattr__(self, 'p2th_address', p2th_address)
        object.__setattr__(self, 'p2th_wif', p2th_wif)
        object.__setattr__(self, 'epoch', epoch) # Epoch in which the transaction was sent. Epochs begin with 0.

    def __str__(self):
        """Replaces btcpy __str__ function, which does only show basic attributes."""
        d = self.__dict__
        strlist = []
        for attr, value in d.items():
            if attr in ("ins", "outs"):
                string = "{}=[{}]".format(attr, ", ".join(str(item) for item in value))
            else:
                string = "{}={}".format(attr, str(value))
            strlist.append(string)

        return 'TrackedTransaction({})'.format(", ".join(strlist))

    def set_proposal(self, proposal):
        # This allows to set the proposal one time per proposal, which should be faster.
        object.__setattr__(self, "proposal", proposal)

    @property
    def txid(self):
        return self._txid # only getter.

    @classmethod
    def get_basicdata(cls, txid, provider):
        json = provider.getrawtransaction(txid, True)
        try:
            import pypeerassets.pautils as pu
            data = pu.read_tx_opreturn(json["vout"][1])
        except KeyError:
            raise InvalidTrackedTransactionError("JSON output:", json)
        return { "data" : data, "json" : json }

    @classmethod
    def from_json(cls, tx_json, provider, network=PeercoinTestnet, deck=None):
        try:

            return cls(
                provider=provider,
                version=tx_json['version'],
                ins=[TxIn.from_json(txin_json) for txin_json in tx_json['vin']],
                outs=[TxOut.from_json(txout_json, network=network) for txout_json in tx_json['vout']],
                locktime=Locktime(tx_json['locktime']),
                txid=tx_json['txid'],
                network=network,
                timestamp=tx_json['time'],
                blockhash=tx_json['blockhash'],
                deck=deck
            )

        except (KeyError, IndexError, ValueError):
            raise InvalidTrackedTransactionError("Transaction without correct datastring or unconfirmed transaction.")



    @classmethod
    def from_txid(cls, txid, provider, network=PeercoinTestnet, deck=None, basicdata=None):
        if basicdata is None:
           basicdata = cls.get_basicdata(txid, provider)
        return cls.from_json(basicdata["json"], provider=provider, network=network, deck=deck)

    def coin_multiplier(self):
        network_params = net_query(self.network.shortname)
        return int(1 / network_params.from_unit) # perhaps to_unit can be used without the division, but it's not sure.

    def get_output_tx(self, tx_list, proposal_state, dist_round, mode: str=None, debug: bool=False):
        # Searches a locking/donation transaction which shares the address of a signalling or reserve transaction

        phase = dist_round // 4
        try:
            # Here we separate ReserveTXes and SignallingTXes
            # If locking mode, then reserve address is ignored even if it exists.
            # (Locking mode searches the DonationTransaction following to a LockingTransaction)
            assert mode != "locking"
            adr = self.reserve_address
        except (AttributeError, AssertionError):
            adr = self.address
        if debug: print("Donor addresses:", proposal_state.donor_addresses)
        if debug: print("Address checked:", adr)
        for tx in tx_list:
            # MODIFIED: added tx type, otherwise the signalling->locking search blocks the locking->donation search.
            # dist_round // 4 represents the phase. You must be able to use the same donor address in phase 1 and 2,
            # due to the reserve transaction question in rd. 4/5.
            if (adr, type(tx), phase) in proposal_state.donor_addresses:
                # TODO: Can this be improved? adr, type(tx), phase should give the same value for many
                # txes of the list, so "continue" isn't the best option.
                # Note: all_locking_txes etc. contain both phases, so it makes sense, but isn't very efficient.
                if debug: print("Rejected, donor address", adr, "already used in this phase for this transaction type.")
                continue
            if debug: print("Input addresses of tx", tx.txid, ":", tx.input_addresses)
            if adr in tx.input_addresses:
                # MODIF: in locking mode, we check the block height of the donation release transaction.
                if mode == "locking":
                    startblock = proposal_state.release_period[0]
                    endblock = proposal_state.release_period[1]

                else:
                    startblock = proposal_state.rounds[dist_round][1][0]
                    endblock = proposal_state.rounds[dist_round][1][1] # last valid block

                if not (startblock <= tx.blockheight <= endblock):
                    continue

                proposal_state.donor_addresses.append((adr, type(tx), phase))
                return tx

        return None

    def get_input_address(self, pubkey_hexstr):
        # calculates input address from pubkey from scriptsig.
        # MODIFIED: we now use directly the btcpy methods. PublicKey.hash() is identic to this.
        pubkey = PublicKey(bytearray.fromhex(pubkey_hexstr))

        #pubkey = bytearray.fromhex(pubkey_hexstr) # or do we need this?
        #round1 = hl.sha256(pubkey).digest()
        #h = hl.new('ripemd160')
        #h.update(round1)
        #pubkey_hash = h.digest()
        return P2pkhAddress(pubkey.hash(), network=self.network).__str__()

    def get_input_address_from_txid(self, txid, txout, provider):
        # mainly for P2PK transactions, where no public key is given in the input.
        inp_txjson = provider.getrawtransaction(txid, 1)
        addr = inp_txjson["vout"][txout]["scriptPubKey"]["addresses"][0]
        return addr


    def set_input_addresses(self, provider=None):
        input_addresses = []
        for inp in self.ins:
            try:
                pubkey_str = inp.script_sig.__str__().split()[1]
                inp_address = self.get_input_address(pubkey_str)
            except IndexError:
                inp_address = self.get_input_address_from_txid(inp.txid, inp.txout, provider)
            input_addresses.append(inp_address)
        return input_addresses


class LockingTransaction(TrackedTransaction):
    """A LockingTransaction is a transaction which locks the donation amount until the end of the
       working period of the Proposer. They are only necessary in the first phase (round 1-4)."""

    def __init__(self, deck, txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, reserve_address=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, p2sh_address=None, epoch=None):

        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

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
                #print("Timelock", public_timelock)
                # public_dest_address_raw = getfmt(self.datastr, fmt, "adr") # this is the address of the pubkey needed to unlock
                # public_dest_address = public_dest_address_raw.decode("utf-8")
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
                    # print("locktime", timelock)
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
        # object.__setattr__(self, 'secret_hash', secret_hash) # secret hash # currently not used

        object.__setattr__(self, 'address', d_address) # address to unlock the redeem script
        object.__setattr__(self, 'amount', d_amount) # donation amount
        object.__setattr__(self, 'p2sh_address', p2sh_address) # P2SH address generated by CLTV script
        object.__setattr__(self, 'redeem_script', redeem_script)

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.

class DonationTransaction(TrackedTransaction):
    """A DonationTransaction is a transaction which transfers the donation to the Proposer."""

    def __init__(self, deck, txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, reserve_address=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, epoch=None):

        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

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

    def __init__(self, deck, txid=None, proposal=None, s_amount=None, s_address=None, dist_round=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, datastr=None, blockhash=None, blockheight=None, p2th_address=None, p2th_wif=None, epoch=None):

        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

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

    def __init__(self, deck, txid=None, donation_address=None, epoch_number=None, round_length=None, req_amount=None, start_epoch=None, round_starts=[], round_txes=[], round_amounts=[], first_ptx_txid=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, datastr=None, p2th_address=None, p2th_wif=None, epoch=None, blockhash=None, blockheight=None):


        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

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
    # => this need some additional considerations: what if a start epoch voter sells his tokens before end epoch?
    # ===> Best would be to ensure that he has at least the same voting power than in start epoch.
    # ===> or update the vote by the balance in round 2? This would be perhaps even better.

    # Vote is always cast with the entire current balance.

    def __init__(self, deck, tx_type=None, txjson=None, txid=None, proposal=None, p2th_address=None, p2th_wif=None, dist_round=None, version=None, ins=[], outs=[], locktime=0, network=PeercoinTestnet, timestamp=None, provider=None, datastr=None, epoch=None, blockheight=None, blockhash=None, vote=None, sender=None):

        TrackedTransaction.__init__(self, txid=txid, txjson=txjson, proposal=proposal, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        if not vote:
            vote = getfmt(self.datastr, VOTING_FORMAT, "vot")
        object.__setattr__(self, "vote", vote)

        if not sender:
            input_tx = self.ins[0].txid
            input_vout = self.ins[0].txout
            #try:
            sender = provider.getrawtransaction(input_tx, 1)["vout"][input_vout]["scriptPubKey"]["addresses"][0]
            #except (KeyError, IndexError): # should normally never happen
            #    raise InvalidTrackedTransactionError("Sender not found.")

        object.__setattr__(self, "sender", sender)

    def set_weight(self, weight):
        object.__setattr__(self, "vote_weight", weight) # TODO: why does "vote_weight" work, but "weight" doesn't???

# Scripts for Timelock contract
# we can use the verify function to extract the locktime from the script.
# Script (with opcodes) -> bytes: compile function
# bytes -> Script: decompile

class DonationTimeLockScript(AbsoluteTimelockScript):

    def __init__(self, raw_locktime, dest_address_string, network=PeercoinTestnet):
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


class InvalidTrackedTransactionError(ValueError):
    # raised anytime when a transacion is not following the intended format.
    pass





