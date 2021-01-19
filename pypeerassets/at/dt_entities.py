#!/usr/bin/env python

"""Basic classes for coin transactions in DT tokens.
Note: All coin amounts are expressed in Bitcoin satoshi, not in "coins" (using the "from_unit" in networks)
This means that the satoshi amounts do not correspond to the minimum unit in currencies like SLM or PPC with less decimal places.

MODIFIED: ProposalState and DonationState are now in dt_states.py."""

from btcpy.structs.script import AbsoluteTimelockScript, Hashlock256Script, IfElseScript, P2pkhScript, ScriptBuilder
from btcpy.structs.address import Address
#from btcpy.lib.parsing import ScriptParser

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.pautils import deck_parser, read_tx_opreturn
from decimal import Decimal
from pypeerassets.kutil import Kutil
from pypeerassets.provider import RpcNode
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, SlimcoinMainnet, SlimcoinTestnet, net_query
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, DONATION_FORMAT, SIGNALLING_FORMAT, LOCKING_FORMAT, VOTING_FORMAT, DEFAULT_VOTING_PERIOD, DEFAULT_SECURITY_PERIOD, DEFAULT_RELEASE_PERIOD


# constants

P2TH_OUTPUT=0 # output which goes to P2TH address
DATASTR_OUTPUT=1 # output with data string (OP_RETURN)
DONATION_OUTPUT=2 # output with donation/signalling amount
RESERVED_OUTPUT=3 # output for a reservation for other rounds.

COIN_MULTIPLIER=100000000 # base unit of PeerAssets is the Bitcoin satoshi with 8 decimals, not the Peercoin/Slimcoin satoshi.

# TODO: TrackedTransactions use the repr function of Transaction, which is incomplete.

class TrackedTransaction(Transaction):
    """A TrackedTransaction is a transaction tracked by the AT or DT mechanisms.
       The class provides the basic features to handle and check transaction attributes comfortably.
       Note: TrackedTransactions are immutable. Once created they can't easily be changed.

       TODO: For some reason this doesn't accept a parameter named json, but txjson works. Investigate! """

    def __init__(self, tx_type=None, txjson=None, txid=None, proposal_txid=None, proposal=None, p2th_address=None, p2th_wif=None, dist_round=None, version=None, ins=[], outs=[], locktime=0, network=PeercoinTestnet, timestamp=None, provider=None, datastr=None, deck=None, epoch=None, blockheight=None, blockhash=None):

        # For security, should later perhaps be replaced by Transaction.__init__()
        # The difference is that here we don't use self.txid, which results in a (relatively expensive) hashing operation.

        if txjson:
            # basic transaction data can be loaded from json
            # TODO seems NOT to work, so probably it needs always the from_json constructor
            self.from_json(txjson, provider, network=network)

        else:
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

        # other attributes come from datastr
        # CONVENTION: datastr is always in SECOND output (outs[1]) like in PeerAssets tx.

        if not datastr:
            try:
                scriptpubkey = self.outs[DATASTR_OUTPUT].script_pubkey
                opreturn_hex = str(scriptpubkey)[10:]
                #print(opreturn_hex)
                datastr = bytes.fromhex(opreturn_hex) # returns bytes.
            except Exception as e: # if no op_return it throws InvalidNulldataOutput
                raise InvalidTrackedTransactionError(ValueError)
        
        object.__setattr__(self, 'datastr', datastr) # OP_RETURN data byte string

        if type(self) == ProposalTransaction:

            if not deck:

                deck_id = getfmt(datastr, PROPOSAL_FORMAT, "dck").hex()
                deckspawntx_json = provider.getrawtransaction(deck_id, True)

                try:
                    deck_p2th_addr = deckspawntx_json["vout"][0]["scriptPubKey"]["addresses"][0]
                except (KeyError, IndexError):
                    raise InvalidTrackedTransactionError(ValueError)

                deck = deck_parser((provider, deckspawntx_json, 1, deck_p2th_addr), True)
                print("No deck found")

            object.__setattr__(self, 'deck', deck)

        else:

            if not proposal_txid:

                if proposal:
                    proposal_txid = proposal.txid
                else:
                    # TODO: workaround: Signalling and Donation datastr format are identic.
                    proposal_txid = getfmt(self.datastr, DONATION_FORMAT, "prp").hex()

            if not proposal:
                # TODO: this is inefficient. We should have to create a ProposalTransaction only once per Proposal.
                # Probably it is also not needed.
                proposal = ProposalTransaction.from_txid(proposal_txid, provider, deck=deck)

            object.__setattr__(self, 'deck', proposal.deck)
            object.__setattr__(self, 'proposal_txid', proposal_txid)
            object.__setattr__(self, 'proposal', proposal)
            # dist_round: in case of Signalling or Donation TXes, the round when they were sent.
            object.__setattr__(self, 'dist_round', dist_round)
        
        # INFO: here was the main inefficiency -> it seems Kutil was called every time.
        # We have to ensure that the deck object is identic for all transactions of the deck (not a copy),
        # so P2TH address is stored.

        if not p2th_address:
            p2th_address = self.deck.derived_p2th_address(tx_type)

        # This seems to be notably slower than P2TH_address
        # Probably we need it only for Bitcoin-0.6 based code
        if not p2th_wif:
            p2th_wif = self.deck.derived_p2th_wif(tx_type)


        object.__setattr__(self, 'p2th_address', p2th_address)
        object.__setattr__(self, 'p2th_wif', p2th_wif) 
        object.__setattr__(self, 'epoch', self.blockheight // self.deck.epoch_length) # Epoch in which the transaction was sent.

    @property
    def txid(self):
        return self._txid # only getter.

    @classmethod
    def get_basicdata(cls, txid, provider):
        json = provider.getrawtransaction(txid, True)
        data = read_tx_opreturn(json["vout"][1])
        return { "data" : data, "json" : json }

    @classmethod
    def from_json(cls, tx_json, provider, network=PeercoinTestnet, deck=None):

        try:
            op_return_hex = tx_json['vout'][1]['scriptPubKey']['asm'][10:]
            #print(op_return_hex)
            datastr = bytes.fromhex(op_return_hex)
            #print(datastr)
        except (KeyError, IndexError, ValueError):
            # TODO: this one should be catched by the Parser.
            raise InvalidTrackedTransactionError("Transaction without correct datastring.")

        return cls(
            provider=provider,
            version=tx_json['version'],
            ins=[TxIn.from_json(txin_json) for txin_json in tx_json['vin']],
            outs=[TxOut.from_json(txout_json) for txout_json in tx_json['vout']],
            locktime=Locktime(tx_json['locktime']),
            txid=tx_json['txid'],
            network=network,
            timestamp=tx_json['time'],
            blockhash=tx_json['blockhash'],
            datastr=datastr,
            deck=deck
        )

    @classmethod
    def from_txid(cls, txid, provider, network=PeercoinTestnet, deck=None):
        d = cls.get_basicdata(txid, provider)
        return cls.from_json(d["json"], provider=provider, network=network, deck=deck)

    def get_input_tx(self, tx_list):
        # searches a transaction which is one of the inputs of the current one in a tx list.
        # MODIFIED: validate does not make sense here. We must allow smaller or bigger donations than signalled amounts,
        # but they would not influence the slot.

        for inp in self.ins:
            txids = [tx.txid for tx in tx_list]
            if inp.txid in txids:
                input_tx = tx_list[txids.index(inp.txid)]
                #if validate:
                #    if input_tx.amount < tx.amount:
                #        return None
                
                return tx_list[txids.index(inp.txid)]
        else:
            return None


    def get_output_tx(self, tx_list):
        # searches a transaction which corresponds to the donation output of a signalling or reserve tx in a tx list.
        for tx in tx_list:
            if self.txid in [ i.txid for i in tx.ins ]:
                # TODO: Look if there is any attack vector if we don't validate the number of the output.
                #if validate:
                #    oup = tx.outs[output]
                #    if oup.amount < t.amount:
                #        return None

                return tx


class LockingTransaction(TrackedTransaction):
    """A LockingTransaction is a transaction which locks the donation amount until the end of the
       working period of the Proposer. They are only necessary in the first phase (round 1-4)."""

    def __init__(self, txid=None, proposal_txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, reserve_address=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, deck=None, epoch=None):
        
        TrackedTransaction.__init__(self, txid=txid, proposal_txid=proposal_txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        if len(outs) > 0:
            # CONVENTION: Donation is in output 2 (0: P2TH, 1: OP_RETURN). 
            # Reserved amount, if existing, is in output 3.
            # TODO: how to handle multiple outputs to donation address? Do we need that?
            locked_out = outs[DONATION_OUTPUT]

            if not d_amount:
                d_amount = locked_out.value # amount in satoshi            

            try:

                if not timelock:
                    timelock = locked_out.script_pubkey.else_script.locktime
                if not d_address:
                     d_address = locked_out.script_pubkey.if_script.address(network=network)

            except AttributeError:
                raise InvalidTrackedTransactionError("Incorrectly formatted LockingTransaction.")

            # elif donation_type == 'DDT':
            #     if not d_address:
            #         d_address = donation_out.script_pubkey.address(network=network)


                    
            if len(outs) > 3 and not reserved_amount:

                reserved_out = outs[RESERVED_OUTPUT]
                reserved_amount = reserved_out.value
                reserve_address = reserved_out.script_pubkey.address(network=network)                

        object.__setattr__(self, 'timelock', timelock)
        # object.__setattr__(self, 'secret_hash', secret_hash) # secret hash # hashlock is disabled!

        # MODIFIED to address and amount (before it was signalled_amount/signalling_address)
        object.__setattr__(self, 'address', d_address) # donation address: the address defined in the referenced Proposal
        object.__setattr__(self, 'amount', d_amount) # donation amount

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.

        # Probably not necessary: # is now managed by DonationState
        # object.__setattr__(self, 'signalling_tx', signalling_tx) # previous signalling transaction, if existing.
        # object.__setattr__(self, 'previous_dtx', previous_dtx) # previous donation transaction, if existing. (for later slot allocations).   

class DonationTransaction(TrackedTransaction):
    """A DonationTransaction is a transaction which transfers the donation to the Proposer."""

    def __init__(self, txid=None, proposal_txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, reserve_address=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, deck=None, epoch=None):
        
        TrackedTransaction.__init__(self, txid=txid, proposal_txid=proposal_txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        try:
            if len(outs) > 0:
                donation_out = outs[DONATION_OUTPUT]

                if not d_amount:
                    d_amount = donation_out.value # amount in satoshi    
                if not d_address:
                    d_address = donation_out.script_pubkey.address(network=network)

            if len(outs) > 3 and not reserved_amount: # we need this for round 5.

                reserved_out = outs[RESERVED_OUTPUT]
                reserved_amount = reserved_out.value
                reserve_address = reserved_out.script_pubkey.address(network=network)


        except AttributeError:
                raise InvalidTrackedTransactionError("Incorrectly formatted DonationTransaction.")



        object.__setattr__(self, 'address', d_address) # donation address: the address defined in the referenced Proposal
        object.__setattr__(self, 'amount', d_amount) # donation amount

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.
    

class SignallingTransaction(TrackedTransaction):
    """A SignallingTransaction is a transaction where a Potential Donor signals available funds."""

    def __init__(self, txid=None, proposal=None, proposal_txid=None, s_amount=Decimal(0), s_address=None, dist_round=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, datastr=None, blockhash=None, blockheight=None, p2th_address=None, p2th_wif=None, deck=None, epoch=None):

        TrackedTransaction.__init__(self, txid=txid, proposal_txid=proposal_txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        if outs:
            # CONVENTION: Signalling is in output 2 (0: P2TH, 1: OP_RETURN).
            signalling_out = outs[2]
            if not s_address:
                s_address = signalling_out.script_pubkey.address(network=network)
            if not s_amount:
                s_amount = signalling_out.value # note: amount is in satoshi

        object.__setattr__(self, 'amount', s_amount)
        # address: the "project specific donation address".
        # To preserve privileges in the later rounds it has to be always the same one.
        object.__setattr__(self, 'address', s_address)


class ProposalTransaction(TrackedTransaction):
    """A ProposalTransaction is the transaction where a DT Proposer specifies required amount and donation address."""
    # Modified: instead of previous_proposal, we use first_ptx_txid. We always reference the first tx.

    def __init__(self, txid=None, deck=None, donation_address=None, epoch_number=None, round_length=None, req_amount=None, start_epoch=None, round_starts=[], round_txes=[], round_amounts=[], first_ptx_txid=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, datastr=None, p2th_address=None, p2th_wif=None, epoch=None, blockhash=None, blockheight=None):


        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        fmt = PROPOSAL_FORMAT

        # this deck_id storage is redundant. It is however perhaps better to do this here.
        # deck_id = getfmt(self.datastr, fmt, "dck").hex() # MODIFIED to hex. check if it does harm.

        epoch_number = int.from_bytes(getfmt(self.datastr, fmt, "eps"), "big")
        round_length = int.from_bytes(getfmt(self.datastr, fmt, "sla"), "big")
        req_amount = int.from_bytes(getfmt(self.datastr, fmt, "amt"), "big") * COIN_MULTIPLIER

        if len(self.datastr) > fmt["ptx"][0] and not first_ptx_txid:
            first_ptx_txid = getfmt(self.datastr, fmt, "ptx").hex()


        # Donation Address. This one must be one from which the ProposalTransaction was signed.
        # Otherwise spammers could confuse the system. # TODO: the check for this.
        # TODO: really spammers would be a problem?
        # CONVENTION for now: It is the address of the FIRST input of the ProposalTransaction.
        # Problem: we need an additional lookup to the tx of the first input to get the address.
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
        object.__setattr__(self, 'first_ptx_txid', first_ptx_txid) # If this is a modification, here goes the Proposal ID.

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

    def __init__(self, tx_type=None, txjson=None, txid=None, proposal_txid=None, proposal=None, p2th_address=None, p2th_wif=None, dist_round=None, version=None, ins=[], outs=[], locktime=0, network=PeercoinTestnet, timestamp=None, provider=None, datastr=None, deck=None, epoch=None, blockheight=None, blockhash=None, vote=None, sender=None):

        TrackedTransaction.__init__(self, txid=txid, txjson=txjson, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

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

# Scripts for HTLC
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


class DonationHashLockScript(Hashlock256Script): # currently not used, because of the problem of a proof for moving transactions.
    def __init__(self, locking_hash, dest_address, network=PeercoinTestnet):
        """first arg: hash, second arg: locked script. """
        dest_address = Address.from_string(dest_address_string, network=network)
        locked_script = P2pkhScript(dest_address)
        super().__init__(locking_hash, locked_script)



class DonationHTLC(IfElseScript): # currently not used, we use DonationTimeLockScript alone.
    """The Donation HTLC is an If-Else-script with the following structure:
       - IF a secret is provided, the Proposer can spend the money. 
       - ELSE if the timelock expires, the Donor can spend the money. """

    def __init__(timelock_address, hashlock_address, raw_locktime, locking_hash, network=PeercoinTestnet):
        hashlockscript = DonationHashLockScript(locking_hash, hashlock_address, network=PeercoinTestnet)
        timelockscript = DonationTimeLockScript(raw_locktime, timelock_address, network=network)
        super().__init__(hashlockscript, timelockscript)

    @staticmethod
    def from_txdata(txjson, vout):
        return ScriptBuilder.identify(txjson["vout"][vout]["scriptPubKey"]["hex"])

    @classmethod
    def from_scriptpubkey(scriptpubkey):
        return cls(scriptpubkey)

    def extract_locktime(self):
        return self.else_script.locktime

    def extract_hash(self):
        return self.if_script.hash

    def extract_proposer_address(self):
        return self.if_script.locked_script.address(network=network)

    def extract_donor_address(self):
        return self.else_script.locked_script.address(network=network)



class InvalidTrackedTransactionError(ValueError):
    # raised anytime when a transacion is not following the intended format.
    pass

    

   

