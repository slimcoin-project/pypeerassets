#!/usr/bin/env python

"""Basic classes for coin transactions in DT tokens.
Note: All coin amounts are expressed in Bitcoin satoshi, not in "coins" (using the "from_unit" in networks)
This means that the satoshi amounts do not correspond to the minimum unit in currencies like SLM or PPC with less decimal places."""

from btcpy.structs.script import AbsoluteTimelockScript, Hashlock256Script, IfElseScript, P2pkhScript, ScriptBuilder
from btcpy.structs.address import Address
#from btcpy.lib.parsing import ScriptParser

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.pautils import deck_parser, read_tx_opreturn
from decimal import Decimal
from pypeerassets.kutil import Kutil
from pypeerassets.provider import RpcNode
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, SlimcoinMainnet, SlimcoinTestnet, net_query
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, DONATION_FORMAT, SIGNALLING_FORMAT, DEFAULT_VOTING_PERIOD, DEFAULT_SECURITY_PERIOD, DEFAULT_RELEASE_PERIOD
from pypeerassets.at.dt_slots import get_slot


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

    def __init__(self, txid=None, proposal_txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, deck=None, epoch=None):
        
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

    def __init__(self, txid=None, proposal_txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, deck=None, epoch=None):
        
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

        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        if not vote:
            vote = getfmt(self.datastr, VOTING_FORMAT, "vot")
        object.__setattr__("vote", vote)

        if not sender:
            input_tx = self.ins[0].txid
            input_vout = self.ins[0].vout
            #try:
            sender = provider.getrawtransaction(input_tx, 1)[input_vout]["scriptPubKey"]["addresses"][0]
            #except (KeyError, IndexError): # should normally never happen
            #    raise InvalidTrackedTransactionError("Sender not found.")

        object.__setattr__("sender", sender)

class ProposalState(object):
   # A ProposalState unifies all functions from proposals which are mutable.
   # i.e. which can change after the first proposal transaction was sent.
   # TODO: For efficiency the getblockcount call should be made in the parser at the start.

    def __init__(self, valid_ptx, first_ptx, round_starts=[], round_halfway=[], signalling_txes=[], donation_txes=[], signalled_amounts=[], locked_amounts=[], donated_amounts=[], effective_slots=[], effective_locking_slots=[], total_donated_amount=None, provider=None, current_blockheight=None, all_signalling_txes=None, all_donation_txes=None, all_locking_txes=None, dist_factor=None):

        self.valid_ptx = valid_ptx # the last proposal transaction which is valid.
        self.first_ptx = first_ptx # first ptx, in the case there was a Proposal Modification.
        # TODO: algorithm has to specify how the first ptx is selected.
        self.req_amount = valid_ptx.req_amount
        self.start_epoch = self.first_ptx.epoch
        self.end_epoch = self.first_ptx.epoch + self.valid_ptx.epoch_number # MODIFIED: first tx is always the base.
        self.donation_address = self.first_ptx.donation_address

        # Slot Allocation Round Attributes are lists with values for each of the 8 distribution rounds
        # We only set this if we need it, because phase 2 varies according to Proposal.
        self.round_starts = round_starts
        self.round_halfway = round_halfway

        deck = self.first_ptx.deck

        if not current_blockheight and (not signalling_txes or not donation_txes):
            current_blockheight = provider.getblockcount()

        # New: Attributes for all TrackedTransactions without checking them (with the exception of VotingTransactions)
        self.all_signalling_txes = all_signalling_txes
        self.all_locking_txes = all_locking_txes
        self.all_donation_txes = all_donation_txes

        # The following attributes are set by the parser once a proposal ends.
        # Only valid transactions are recorded in them.
        self.signalling_txes = signalling_txes
        self.signalled_amounts = signalled_amounts
        self.locking_txes = locking_txes
        self.locked_amounts = locked_amounts
        self.donation_txes = donation_txes
        self.donated_amounts = donated_amounts
        self.donation_states = donation_states
        self.total_donated_amount = total_donated_amount

        # The effective slot values are the sums of the effective slots in each round.
        self.effective_locking_slots = effective_locking_slots
        self.effective_slots = effective_slots

        # Factor to be multiplied with token amounts, between 0 and 1.
        # It depends on the Token Quantity per distribution period
        # and the number of coins required by the proposals in their ending period.
        # The higher the amount of proposals and their required amounts, the lower this factor is.
        self.dist_factor = dist_factor


    def set_round_starts(self, phase=0):
        # all rounds of first or second phase
        # It should be ensured that this method is only called once per phase, or when a proposal has been modified.

        epoch_length = self.valid_ptx.deck.epoch_length
        pre_allocation_period = DEFAULT_SECURITY_PERIOD + DEFAULT_VOTING_PERIOD # for now hardcoded, should be variable.

        self.round_starts = [None] * 8
        self.round_halfway = [None] * 8
        halfway = self.first_ptx.round_length // 2

        # phase 0 means: both phases are calculated.

        if phase in (0, 1):
            distribution_length = pre_allocation_period + (self.first_ptx.round_length * 4)
            # blocks in epoch: blocks which have passed since last epoch start.
            blocks_in_epoch = (self.first_ptx.blockheight - (self.start_epoch - 1) * epoch_length)
            blocks_remaining = epoch_length - blocks_in_epoch
            

            # if proposal can still be voted, then do it in the current period
            if blocks_remaining > distribution_length:

                phase_start = self.blockheight + pre_allocation_period
            else:
                phase_start = self.start_epoch * epoch_length + pre_allocation_period # next epoch

            for i in range(4): # first phase has 4 rounds
                self.round_starts[i] = phase_start + self.first_ptx.round_length * i
                self.round_halfway[i] = self.round_starts[i] + halfway

                 
        if phase in (0, 2):

            epoch = self.end_epoch # final vote/distribution should always begin at the start of the end epoch.

            phase_start = self.end_epoch * epoch_length + pre_allocation_period + DEFAULT_RELEASE_PERIOD

            for i in range(5): # second phase has 5 rounds, the last one being the Proposer round.
                # we use valid_ptx here, this gives the option to change the round length of 2nd round.
                self.round_starts[i + 4] = phase_start + self.valid_ptx.round_length * i
                self.round_halfway[i + 4] = self.round_starts[i + 4] + halfway

            # print(self.round_starts)

    def set_donation_states(self, phase=0):
        # Version3. Uses the new DonationState class and the generate_donation_states method. 
        # Phase 0 means both phases are calculated.

        # If round starts are not set, or phase is 2 (re-defining of the second phase), then we set it.
        if len(self.round_starts) == 0 or (phase == 2):
            self.set_round_starts(phase)
            
        dstates = [{} for i in range(8)] # dstates is a list containing a dict with the txid of the signalling transaction as key
        rounds = (range(8), range(4), range(4,8))

        for rd in rounds[phase]:
            dstates[rd] = self._process_donation_states(rd)

        if phase in (0,1):
            self.donation_states = dstates
        elif phase == 2:
            self.donation_states[4:] = dstates[4:]

        self.total_donated_amount = sum(self.donated_amounts)


    def _process_donation_states(self, rd):
        # This function always must run chronologically, with previous rounds already completed.
        # It can, however, be run to redefine phase 2 (rd 4-7).
        # It sets also the attributes that are necessary for the next round and its slot calculation.

        # 1. determinate the valid signalling txes (include reserve/locking txes). 
        dstates = {}
        donation_tx, locking_tx, effective_locking_slot, effective_slot = None, None, None, None

        all_stxes = [ stx for stx in self.all_signalling_txes if self.get_stx_dist_round == rd ]
        if rd in (0, 3, 6, 7):
             # first round, round 6 and first-come-first-serve rds: all signalling txes inside the blockheight limit.
             valid_stxes = all_stxes
             valid_rtxes = [] # No RTXes in these rounds.
        else:
             # TODO: Could be made more efficient, if necessary.
             if rd in (1, 2):
                 all_rtxes = [ltx for ltx in self.locking_txes[rd - 1] if ltx.reserved_amount > 0]
             elif rd == 4:
                 all_rtxes = [dtx for r in self.donation_txes[:4] for dtx in r if dtx.reserved_amount > 0]
             else:
                 all_rtxes = [dtx for dtx in self.donation_txes[rd - 1] if dtx.reserved_amount > 0]
             #stxes = [ stx for stx in all_stxes if self.validate_priority(stx, rd) == True ]          
             #rtxes = [ rtx for rtx in all_rtxes if self.validate_priority(rtx, rd) == True ]
             valid_stxes = self.validate_priority(all_stxes, rd)
             valid_rtxes = self.validate_priority(all_rtxes, rd)  

        # 2. Calculate total signalled amount and set other variables.

        self.signalling_txes[rd] = valid_stxes
        self.signalled_amounts[rd] = sum([tx.amount for tx in valid_stxes])
        self.reserve_txes[rd] = valid_rtxes
        self.reserved_amounts[rd] = sum([tx.reserved_amount for tx in valid_rtxes])
        # self.total_signalled_amount[rd] = self.signalled_amount + self.reserved_amount # Probably not needed.

        # 3. Generate DonationState and add locking/donation txes:
        # TODO: Do we need to validate the correct round of locking/donation, and even reserve txes?
        for tx in (valid_stxes + valid_rtxes):
            slot = get_slot(tx, rd, proposal_state=self)
            if rd < 4:
                locking_tx = tx.get_output_tx(self.all_locking_txes)
                # If the timelock is not correct, locking_tx is not added, and no donation tx is taken into account.
                # The DonationState will be incomplete in this case. Only the SignallingTx is being added.
                if self.validate_timelock(locking_tx):
                    self.locking_txes[rd].append(locking_tx)
                    self.locked_amounts[rd] + locking_tx.amount
                    effective_locking_slot = min(slot, locking_tx.amount)
                    donation_tx = locking_tx.get_output_tx(self.all_donation_txes)
            else:
                donation_tx = tx.get_output_tx(self.all_donation_txes)

            if donation_tx:
                effective_slot = min(slot, donation_tx.amount)
                self.donation_txes[rd].append(donation_tx)
                self.donated_amounts[rd] += donation_tx.amount

            # In round 1-4, the effectively locked slot amounts are the values which determinate the
            # slot rest for the next round. In round 5-8 it's the Donation effective slots.
            if effective_locking_slot:
                self.effective_locking_slots[rd] += effective_locking_slot
            if effective_slot:
                self.effective_slots[rd] += effective_slot
            
            dstate = DonationState(signalling_tx=tx, locking_tx=locking_tx, donation_tx=donation_tx, slot=slot, effective_slot=effective_slot, effective_locking_slot=effective_locking_slot, amount=donation_tx.amount, dist_round=rd)
    
            dstates.update({dstate.signalling_tx.txid, dstate})

        return dstates
               
    def get_stx_dist_round(self, stx):
        # This one only checks for the blockheight. Thus it can only be used for stxes.
       for rd in range(8):
           start = self.round_starts[rd]
           end = self.round_halfway[rd]

           if start <= stx.blockheight < end:
               return rd
           else:
               # raise InvalidTrackedTransactionError("Incorrect blockheight for a signalling transaction.")
               return None

    def set_dist_factor(self, ending_proposals):
        # Proposal factor: if there is more than one proposal ending in the same epoch,
        # the resulting slot is divided by the req_amounts of them.
        # This is set in the function dt_parser_utils.get_valid_ending_proposals.

        # ending_proposals = [p for p in pst.valid_proposals.values() if p.end_epoch == proposal_state.end_epoch]

        # print("Ending proposals in the same epoch than the one referenced here:", ending_proposals)

        if len(ending_proposals) > 1:
            total_req_amount = sum([p.req_amount for p in ending_proposals])
            self.dist_factor = Decimal(self.req_amount) / total_req_amount
        else:
            self.dist_factor = Decimal(1)

        # print("Dist factor", self.dist_factor)


    def validate_priority(self, tx_list, dist_round):
        """Validates the priority of signalling and reserve transactions in round 2, 3, 5 and 6."""
        # New version with DonationStates, modified to validate a whole round list at once (more efficient).
        # Should be optimized in the beta/release version.
        # The type test seems ugly but is necessary unfortunately. All txes given to this method have to be of the same type.
        valid_txes = []
        if dist_round in (0, 3, 6, 7):
            return tx_list # rounds without priority check

        elif dist_round == 4: # rd 5 is special because all donors of previous rounds are admitted.

            valid_dstates = [dstate for rd in (0, 1, 2, 3) for dstate in self.donation_states[rd]]
            if type(tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates]
        elif dist_round == 5:

            valid_dstates = [dstate for dstate in self.donation_states[4]]
            if type(tx_list[0]) == DonationTransaction:
                valid_rtx_txids = [dstate.donation_tx.txid for dstate in valid_dstates]        
        elif dist_round in (1, 2):
            valid_dstates = [dstate for dstate in self.donation_states[dist_round - 1]]
            if type(tx_list[0]) == LockingTransaction:
                valid_rtx_txids = [dstate.locking_tx.txid for dstate in valid_dstates]

        # Locking or DonationTransactions: we simply look for the DonationState including it
        # If it's not in any of the valid states, it can't be valid.
        for tx in tx_list:
            if type(tx) in (LockingTransaction, DonationTransaction):
                try:
                    tx_dstate = valid_dstates[valid_rtx_txids.index(tx.txid)]
                except IndexError:
                    continue
            # In the case of signalling transactions, we must look for donation/locking TXes
            # using the same spending address.
            # TODO: Input or output addr?
            elif type(tx) == SignallingTransaction:
                for dstate in valid_dstates:
                    if tx.address == dstate.donor_address:
                        tx_dstate = dstate
                        
            else:
                continue

            if (dist_round < 4) and (tx_dstate.locking_tx.amount >= tx_dstate.slot): # we could use the "complete" attribute? or only in the case of DonationTXes?
                valid_txes.append(tx)
            elif (dist_round >= 4) and (tx_dstate.donation_tx.amount >= tx_dstate.slot):
                valid_txes.append(tx)
        return valid_txes
               
    def validate_timelock(self, ltx):
        """Checks that the timelock of the donation is correct."""

        # Timelock must be set at least to the block height of the start of the end epoch.
        # We take the value of the first ProposalTransaction here, because in the case of Proposal Modifications,
        # all LockedTransactions need to stay valid.

        original_phase2_start = (self.first_ptx.start_epoch + self.first_ptx.epoch_number) * self.deck.epoch_length

        if ltx.timelock >= original_phase2_start:
            return True
        else:
            return False
        
class DonationState(object):
    # A DonationState contains Signalling, Locked and Donation transaction and the slot.
    # Must be created always with either SignallingTX or ReserveTX.

    def __init__(self, signalling_tx=None, reserve_tx=None, locking_tx=None, donation_tx=None, slot=None, dist_round=None, effective_slot=None, effective_locking_slot=None):
        self.signalling_tx = signalling_tx
        self.reserve_tx = reserve_tx
        self.locking_tx = locking_tx
        self.donation_tx = donation_tx
        self.donated_amount = donation_tx.amount
        self.dist_round = dist_round
        self.slot = slot
        self.effective_slot = effective_slot
        self.effective_locking_slot = effective_locking_slot

        if signalling_tx:
            self.donor_address = signalling_tx.address
            self.signalled_amount = signalling_tx.amount
        elif reserve_tx:
            self.donor_address = reserve_tx.reserve_address
            self.reserved_amount = reserve_tx.reserved_amount
        else:
            raise InvalidDonationStateError("A DonationState must be initialized with a signalling or reserve address.")

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

class InvalidDonationStateError(ValueError):
    # raised anytime when a DonationState is not following the intended format.
    pass

    

   

