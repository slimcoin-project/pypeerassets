#!/usr/bin/env python

# basic classes for coin transactions in DT tokens
# IMPORTANT MODIFICATION: All amounts are now expressed in satoshi, not in "coins" (using the "from_unit" in networks).

from btcpy.structs.script import AbsoluteTimelockScript, BaseScript
from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.pautils import deck_parser, read_tx_opreturn
from decimal import Decimal
from pypeerassets.kutil import Kutil
from pypeerassets.provider import RpcNode
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, SlimcoinMainnet, SlimcoinTestnet, net_query
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, DONATION_FORMAT, SIGNALLING_FORMAT, DEFAULT_VOTING_PERIOD, DEFAULT_SECURITY_PERIOD


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

    #@property
    def dist_round(self):
        # sets round of donation/signalling tx
        # should normally be done from outside.
        try:

            for rd in range(8):
                min_blockheight = self.proposal.get_round_start(rd)
                max_blockheight = self.proposal.get_round_start(rd) + (proposal.round_length - 1) # last block of current round
                if self.blockheight > min_blockheight and self.blockheight <= max_blockheight:
                    object.__setattr__(self, 'dist_round', rd)

        except AttributeError: # if self.proposal not set
            object.__setattr__(self, 'dist_round', None)

    @classmethod
    def get_basicdata(cls, txid, provider):
        json = provider.getrawtransaction(txid, True)
        data = read_tx_opreturn(json["vout"][1])
        return { "data" : data, "json" : json }

    @classmethod
    def from_json(cls, tx_json, provider, network=PeercoinTestnet, deck=None):
        # identifier = read_tx_opreturn(tx_json["vout"][1])[:2]
        #if identifier == b'DP':
        #    tx_type="proposal"
        #elif identifier == b'DS':
        #    tx_type="signalling"
        #elif identifier == b'DD':
        #    tx_type="donation"
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


class DonationTransaction(TrackedTransaction):
    """A DonationTransaction is a transaction which can lead to AT or DT issuances."""
    # TODO: Do we need to handle ProposalState object here?

    def __init__(self, txid=None, proposal_txid=None, proposal=None, timelock=None, secret_hash=None, d_address=None, d_amount=None, reserved_amount=None, signalling_tx=None, previous_dtx=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, blockheight=None, blockhash=None, datastr=None, p2th_address=None, p2th_wif=None, deck=None, epoch=None):
        
        TrackedTransaction.__init__(self, txid=txid, proposal_txid=proposal_txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        if outs:
            # CONVENTION: Donation is in output 2 (0: P2TH, 1: OP_RETURN). 
            # Reserved amount is in output 3.
            # Note: In Direct Donation Transactions, timelock should be set to 0, not None.
            # TODO: how to handle multiple outputs to donation address? Do we need that?
            donation_out = outs[DONATION_OUTPUT]

            if not timelock:
                timelock = self.extract_timelock(donation_out)
            if not secret_hash and (timelock != 0):
                secret_hash = self.extract_shash(donation_out)
            if not d_address:
                d_address = donation_out.script_pubkey.address(network=network)
            if not d_amount:
                d_amount = donation_out.value # amount in satoshi

            if not reserved_amount and len(outs) > 3:

                reserved_out = outs[RESERVED_OUTPUT]
                reserved_amount = reserved_out.value
                

        object.__setattr__(self, 'timelock', timelock)
        object.__setattr__(self, 'secret_hash', secret_hash) # secret hash

        # MODIFIED to address and amount (before it was signalled_amount/signalling_address)
        object.__setattr__(self, 'address', d_address) # donation address: the address defined in the referenced Proposal
        object.__setattr__(self, 'amount', d_amount) # donation amount

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'signalling_tx', signalling_tx) # previous signalling transaction, if existing.
        object.__setattr__(self, 'previous_dtx', previous_dtx) # previous donation transaction, if existing. (for later slot allocations).   

    def extract_timelock(self, out):
        # gets timelock expiration from transaction data.
        # TODO: this needs a bit of Bitcoin Script knowledge.
        # TODO: maybe unite both functions?
        return None

    def extract_shash(self, out):
        # extracts secret hash from transaction data.
        # TODO: this needs a bit of Bitcoin Script knowledge.
        return None
    

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

        # MODIFIED to address and amount (before it was signalled_amount/signalling_address)
        object.__setattr__(self, 'amount', s_amount)
        object.__setattr__(self, 'address', s_address) # perhaps useful for some checks.


class ProposalTransaction(TrackedTransaction):
    """A ProposalTransaction is the transaction where a DT Proposer specifies required amount and donation address."""
    # Modified: instead of previous_proposal, we use first_ptx_txid. We always reference the first tx.

    def __init__(self, txid=None, deck=None, donation_address=None, epoch_number=None, round_length=None, req_amount=None, start_epoch=None, round_starts=[], round_txes=[], round_amounts=[], first_ptx_txid=None, json=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, provider=None, datastr=None, p2th_address=None, p2th_wif=None, epoch=None, blockhash=None, blockheight=None):


        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        fmt = PROPOSAL_FORMAT

        # this deck_id storage is redundant. It is however perhaps better to do this here.
        # deck_id = getfmt(self.datastr, fmt, "dck").hex() # MODIFIED to hex. check if it does harm.

        # this is the multiplier to the "coin" based req_amount (the number of satoshis for a COIN)
        # coin_multiplier = int(1 / getattr(network, "from_unit"))
        # seems wrong, PA uses the satoshi from Bitcoin as base. So we make a constant (see above)


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
    # TODO: Also, we could implement a partial vote. But that would not really make sense and make things more complex.

    def __init__(self, tx_type=None, txjson=None, txid=None, proposal_txid=None, proposal=None, p2th_address=None, p2th_wif=None, dist_round=None, version=None, ins=[], outs=[], locktime=0, network=PeercoinTestnet, timestamp=None, provider=None, datastr=None, deck=None, epoch=None, blockheight=None, blockhash=None, vote=None, sender=None):

        TrackedTransaction.__init__(self, txid=txid, txjson=json, datastr=datastr, p2th_address=p2th_address, p2th_wif=p2th_wif, version=version, ins=ins, outs=outs, locktime=locktime, network=network, timestamp=timestamp, provider=provider, deck=deck, epoch=epoch, blockheight=blockheight, blockhash=blockhash)

        if not vote:
            vote = getfmt(self.datastr, VOTING_FORMAT, "vot")
        object.__setattr__("vote", vote)

        if not sender:
            input_tx = self.ins[0].txid
            input_vout = self.ins[0].vout
            try:
                sender = provider.getrawtransaction(input_tx, 1)[input_vout]["scriptPubKey"]["addresses"][0]
            except (KeyError, IndexError): # should normally never happen
                raise InvalidTrackedTransactionError("Sender not found.")

        object.__setattr__("sender", sender)



class ProposalState(object):
   # A ProposalState unifies all functions from proposals which are mutable.
   # i.e. which can change after the first proposal transaction was sent.
   # TODO: For efficiency the getblockcount call should be made in the parser at the start.

    def __init__(self, valid_ptx, first_ptx, round_starts=[], signalling_txes=[], donation_txes=[], signalled_amounts=[], locked_amounts=[], donated_amounts=[], provider=None, current_blockheight=None, all_signalling_txes=None, all_donation_txes=None):

        self.valid_ptx = valid_ptx # the last proposal transaction which is valid.
        self.first_ptx = first_ptx # first ptx, in the case there was a Proposal Modification.
        # TODO: algorithm has to specify how the first ptx is selected.
        self.req_amount = valid_ptx.req_amount
        self.start_epoch = self.first_ptx.epoch
        self.end_epoch = self.first_ptx.epoch + self.valid_ptx.epoch_number # MODIFIED: first tx is always the base.

        # round attributes -> are lists with values for each of the 8 distribution rounds
        #if not round_starts:
        #    self.set_round_starts()
        #else:
        #    self.round_starts = round_starts

        # MODIFIED: we only set this if we need it, because phase 2 varies according to Proposal.
        self.round_starts = round_starts 

        deck = self.first_ptx.deck

        if not current_blockheight and (not signalling_txes or not donation_txes):
            current_blockheight = provider.getblockcount()

        # the following are normally set from parser when proposal ends.
        self.signalling_txes = signalling_txes
        self.signalled_amounts = signalled_amounts
        

        self.locked_amounts = locked_amounts # this is only used during the proposal lifetime (between start and end)
        self.donation_txes = donation_txes
        self.donated_amounts = donated_amounts
        
    @property
    def extract_donation_address(self):
         # extracts address from sending output.
        pass

    def extract_expiration(self):
        # extracts expiration from OP_RETURN
        pass

    def set_round_starts(self, phase=0):
        # all rounds of first or second phase
        # TODO: We probably do not need round 9, as it's the proposer Issuance round (if Proposer doesn't claim the tokens, nothing gets modified, and he can claim at any time).
        # TODO: It should be ensured that this method is only called once per phase, or when proposal has been modified.

        epoch_length = self.valid_ptx.deck.epoch_length
        pre_allocation_period = DEFAULT_SECURITY_PERIOD + DEFAULT_VOTING_PERIOD # for now hardcoded, should be variable.

        #if len(self.round_txes) == 0: # what is that?
        #    self.round_starts = [[]] * 9
        self.round_starts = [None] * 9

        # phase 0 means: both phases are calculated.

        if phase in (0, 1):
            distribution_length = pre_allocation_period + (self.first_ptx.round_length * 4) # or better first ptx?
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

                 
        if phase in (0, 2):

            epoch = self.end_epoch # final vote/distribution should always begin at the start of the end epoch.

            phase_start = self.end_epoch * epoch_length + pre_allocation_period

            for i in range(5): # second phase has 5 rounds
                # we use valid_ptx here, this gives the option to change the round length of 2nd round.
                self.round_starts[i + 4] = phase_start + self.valid_ptx.round_length * i

            print(self.round_starts)


    def get_round_start(self, dist_round):
        # This is probably largely obsolete. It doesn't make sense to set this number individually per round, as the calculation amount is very low.
        # We could neet this however for the application which shows selected donations and slots.
  
        epoch_length = self.valid_ptx.deck.epoch_length
        pre_allocation_period = SECURITY_PERIOD + VOTING_PERIOD 

        if len(self.round_txes) == 0:
            self.round_starts = [[]] * 9

        if dist_round < 5:
            distribution_length = pre_allocation_period + (self.first_ptx.round_length * 4) # or better first ptx?
            # blocks in epoch: blocks which have passed since last epoch start.
            blocks_in_epoch = (self.first_ptx.blockheight - (self.start_epoch - 1) * epoch_length)
            blocks_remaining = epoch_length - blocks_in_epoch

            # - should this be integrated as "voting_epoch" into proposal object ??
            if blocks_remaining > distribution_length:
                epoch = self.start_epoch
            else:
                epoch = self.start_epoch + 1

            period_round = dist_round # in period 1, dist_round is equivalent to period_round.
                 
        else:
            epoch = self.end_epoch # final vote/distribution should always begin at the start of the end epoch.
            period_round = dist_round - 4 # round 5 is round 1 of second period.

        epoch_start = (epoch - 1) * epoch_length
        round_start = epoch_start + pre_allocation_period + ((period_round - 1)* round_length)

        self.round_starts[dist_round] = round_start

    # @property
    # TODO changed: if it's a property it interferes with __init__
    # MODIFIED: this now only addes txes, is not used anymore in __init__. Should be used per round.
    def add_signalling_txes(self, all_signalling_txes):
        for tx in all_signalling_txes:
            if (tx.proposal_txid == self.txid) and (tx not in self.donation_txes):
                signalling_txes.append(tx)
        return signalling_txes

    # @property
    def add_donation_txes(self, all_donation_txes):
        # TODO: must DDT transactions be treated differently than timelocked transactions?
        for tx in all_donation_txes:
            if (tx.proposal_txid == self.txid) and (tx not in self.donation_txes):
                donation_txes.append(tx)
        return donation_txes
         

    def get_round_txes(self, dist_round, txes):
        # gets the donation or signalling txes in a round. Does not need a pre-selection by proposal (TODO: see if this is the most efficient approach).
        # Probably largely obsolete, except for the app which shows slots when they are distributed.
        # dist_round starts at 0.
        # argument for 1: we can use 0 to use the start of dist_round 1.
        # but what to do with round 5 (first round of period 2)?
        min_blockheight = self.get_round_start(dist_round)
        max_blockheight = self.get_round_start(dist_round) + (ptx.round_length - 1) # - 1 because otherwise next round start block would be included.

        # gets all txes which compete in a specified distribution round for a Proposal (ptx=proposal transaction).
        for tx in txes:

            if tx.proposal != self.txid:
                continue

            if tx.blockheight < min_blockheight:
                continue
            elif tx.blockheight >= max_blockheight:
                break # assumes strict chronological order in listtransactions. TODO: check that!

        round_txes[dist_round].append[tx]
        return round_txes


    def set_phase_txes_and_amounts(self, txes, tx_type, phase=0):
        # This is the main loop called in __init__
        # sets the donation or signalling txes and amounts in ALL rounds of a phase, or in both phases.
        # phase 0: both phases are done
        # TODO: self.donated_amounts in phase 1 needs a check for locked and moved amounts.

        if len(self.round_starts) == 0: # TODO: check if we must differentiate per phase in check!
            self.set_round_starts(phase)
        
        round_length = self.valid_ptx.round_length
        mid_value = round_length // 2 # signalling length is slightly smaller if round length is not par


        round_txes = [[],[],[],[],[],[],[],[],[]] # [[]] * 9 leads to a strange bug, appends to all elements
        round_amounts = [0, 0, 0, 0, 0, 0, 0, 0, 0]

        
        if tx_type == "signalling":
            start_offset = 0
            end_offset = mid_value
        elif tx_type == "donation":
            start_offset = mid_value
            end_offset = round_length - 1

        if phase == 0:
            rounds = list(range(8))
        elif phase == 1:
            rounds = range(4)
        elif phase == 2:
            rounds = range(4, 8)

        for tx in txes:

            if tx.proposal.txid != self.first_ptx.txid: # valid or first ptx? # donation txes always reference first one
                continue
            # print("Checking tx", tx.txid, "of type", tx_type, "at block", tx.blockheight, "Round starts:", self.round_starts)

            for rd in rounds:

                rd_start, rd_end = self.round_starts[rd] + start_offset, self.round_starts[rd] + end_offset

                if rd_start <= tx.blockheight and tx.blockheight < rd_end:

                    round_txes[rd].append(tx)
                    round_amounts[rd] += tx.amount

        # print("Round txes:", round_txes)

        if tx_type == "signalling":

            if not self.signalling_txes or (phase in (0, 1)): # this should never be called to re-define phase 1.

                self.signalling_txes = round_txes
                self.signalled_amounts = round_amounts

            elif phase == 2:
                self.signalling_txes[4:] = round_amounts[4:]


        elif tx_type == "donation":

            if not self.donation_txes or (phase in (0, 1)):

                self.donation_txes = round_txes
                self.donated_amounts = round_amounts

            elif phase == 2:
                self.donation_txes[4:] = round_amounts[4:]

    def get_round_amounts(self, dist_round, txes, tx_type="signalling"):
        # can be used for signalling, locked and donated amounts.
        if len(self.round_amounts) == 0:
            self.round_amounts = [[]] * 9
        amount = Decimal(0)
        for tx in self.get_round_txes(txes, dist_round):
            amount += tx.signalled_amount
        self.round_amounts[dist_round] = amount


class DonationTimeLockScript(AbsoluteTimelockScript):

    def __init__(raw_locktime, dest_address):
        """
        :param args: if one arg is provided it is interpreted as a script, which is in turn
        verified and `locktime` and `locked_script` are extracted. If two args are provided,
        they are interpreted as `locktime` and `locked_script` respectively, the script is
        then generated from these params
        """
        locktime = Locktime(raw_locktime)
        locked_script = BaseScript(dest_address)
        super().__init__(locktime, locked_script)

class DonationHashLockScript():
    pass


class InvalidTrackedTransactionError(ValueError):
    # raised anytime when a transacion is not following the intended format.
    pass

    

   

