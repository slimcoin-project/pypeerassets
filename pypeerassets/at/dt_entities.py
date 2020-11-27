#!/usr/bin/env python

"""Basic classes for coin transactions in DT tokens.
Note: All coin amounts are expressed in Bitcoin satoshi, not in "coins" (using the "from_unit" in networks)
This means that the satoshi amounts do not correspond to the minimum unit in currencies like SLM or PPC with less decimal places."""

from btcpy.structs.script import AbsoluteTimelockScript, HashlockScript, IfElseScript, P2pkhScript, ScriptBuilder
from btcpy.structs.address import Address
#from btcpy.lib.parsing import ScriptParser

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.pautils import deck_parser, read_tx_opreturn
from decimal import Decimal
from pypeerassets.kutil import Kutil
from pypeerassets.provider import RpcNode
from pypeerassets.networks import PeercoinMainnet, PeercoinTestnet, SlimcoinMainnet, SlimcoinTestnet, net_query
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, DONATION_FORMAT, SIGNALLING_FORMAT, DEFAULT_VOTING_PERIOD, DEFAULT_SECURITY_PERIOD
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

            if not d_amount:
                d_amount = donation_out.value # amount in satoshi            

            if not donation_type:

                # We check the structure of the ScriptPubKey to determine the transaction type.
                if type(donation_out.script_pubkey) == P2pkhScript: # Direct Donation Transactions are simple P2pkh Scripts
                    donation_type = 'DDT'
                elif type(donation_out.script_pubkey) == IfElseScript: # HTLC
                    donation_type = 'HTLC'

            if donation_type == 'HTLC':
                try:

                    if not timelock:
                        timelock = donation_out.script_pubkey.else_script.locktime
                    if not secret_hash:
                        secret_hash = donation_out.script_pubkey.if_script.secret_hash
                    if not d_address:
                        d_address = donation_out.script_pubkey.if_script.address(network=network)

                except AttributeError:
                    raise InvalidTrackedTransactionError("Incorrectly formatted HTLC.")

            elif donation_type == 'DDT':
                if not d_address:
                    d_address = donation_out.script_pubkey.address(network=network)


                    
            if len(outs) > 3 and not reserved_amount:

                reserved_out = outs[RESERVED_OUTPUT]
                reserved_amount = reserved_out.value
                reserve_address = reserved_out.script_pubkey.address(network=network)
                

        object.__setattr__(self, 'donation_type', donation_type)
        object.__setattr__(self, 'timelock', timelock)
        object.__setattr__(self, 'secret_hash', secret_hash) # secret hash

        # MODIFIED to address and amount (before it was signalled_amount/signalling_address)
        object.__setattr__(self, 'address', d_address) # donation address: the address defined in the referenced Proposal
        object.__setattr__(self, 'amount', d_amount) # donation amount

        object.__setattr__(self, 'reserved_amount', reserved_amount) # Output reserved for following rounds.
        object.__setattr__(self, 'reserve_address', reserve_address) # Output reserved for following rounds.

        # TODO: these two are still not implemented, but maybe are not necessary. We keep them for now.
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
        # address: the "project specific donation address". To preserve privileges in the later rounds it has to be always the same one.
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

    def __init__(self, valid_ptx, first_ptx, round_starts=[], signalling_txes=[], donation_txes=[], signalled_amounts=[], locked_amounts=[], donated_amounts=[], total_donated_amount=None, provider=None, current_blockheight=None, all_signalling_txes=None, all_donation_txes=None, dist_factor=None):

        self.valid_ptx = valid_ptx # the last proposal transaction which is valid.
        self.first_ptx = first_ptx # first ptx, in the case there was a Proposal Modification.
        # TODO: algorithm has to specify how the first ptx is selected.
        self.req_amount = valid_ptx.req_amount
        self.start_epoch = self.first_ptx.epoch
        self.end_epoch = self.first_ptx.epoch + self.valid_ptx.epoch_number # MODIFIED: first tx is always the base.

        # Slot Allocation Round Attributes are lists with values for each of the 8 distribution rounds
        # We only set this if we need it, because phase 2 varies according to Proposal.
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
        self.total_donated_amount = total_donated_amount

        # Factor to be multiplied with token amounts.
        # It depends on the Token Quantity per distribution period
        # and the number of coins required by the proposals in the ending period. 

        self.dist_factor = dist_factor 


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

    def set_phase_txes_and_amounts(self, txes, tx_type, phase=0):
        # sets the donation or signalling txes and amounts in all rounds of a phase, or in both phases.
        # phase 0 means both phases
        # TODO: self.donated_amounts in phase 1 needs a check for locked and moved amounts.
        # TODO: set reserved amounts and locked amounts.

        if len(self.round_starts) == 0: # TODO: check if we must differentiate per phase in check!
            self.set_round_starts(phase)
        
        round_length = self.valid_ptx.round_length
        mid_value = round_length // 2 # signalling length is slightly smaller if round length is not par


        round_txes = [[],[],[],[],[],[],[],[],[]] # [[]] * 9 leads to a strange bug, appends to all elements
        round_amounts = [0, 0, 0, 0, 0, 0, 0, 0, 0]
        completed_donations = [[],[],[],[],[],[],[],[],[]]
        donated_amounts = [0, 0, 0, 0, 0, 0, 0, 0, 0]

        
        if tx_type == "signalling":
            start_offset = 0
            end_offset = mid_value
        elif tx_type == "donation":
            start_offset = mid_value
            end_offset = round_length - 1

        if phase == 0:
            rounds = range(8)
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
                    # special rules for round 2/3 and 5/6 (priority groups)
                    if (tx_type == "signalling") and (not self.validate_priority(tx, rd)):
                        break

                    if tx_type == "donation":
                        # check of the timelock in round 1-4.
                        if not self.validate_timelock(tx, rd)):
                            break
                        # to be added to completed donations, in rd 1-4 it is necessary
                        # that the vout is moved to the Proposer.

                        if (rd >= 4) or (was_vout_moved(self.provider, tx)):
                            completed_donations[rd].append(tx)
                            donated_amounts[rd] += tx.amount
                        
                    round_txes[rd].append(tx)
                    round_amounts[rd] += tx.amount

                    # check for completed donations
                    break

        # print("Round txes:", round_txes)

        if tx_type == "signalling":

            if not self.signalling_txes or (phase in (0, 1)): # this should never be called to re-define phase 1.

                self.signalling_txes = round_txes
                self.signalled_amounts = round_amounts

            elif phase == 2:

                self.signalling_txes[4:] = round_txes[4:]
                self.signalled_amounts[4:] = round_amounts[4:]


        elif tx_type == "donation":

            # As the timelock was checked here, all tx amounts can be added to locked_amounts.
            # It is only added to donated amounts if it is in phase 5+ or the output was already moved, or it is a DDT.
            if not self.donation_txes or (phase in (0, 1)):

                self.donation_txes = round_txes
                self.locked_amounts = round_amounts


            elif phase == 2:
                self.donation_txes[4:] = round_txes[4:]
                self.locked_amounts[4:] = round_amounts[4:]

            if phase in (0,2): # these values are set at the end of all calculations.

                self.completed_donations = completed_donations
                self.donated_amounts = donated_amounts
                self.total_donated_amount = sum(self.donated_amounts)

    def set_dist_factor(self, ending_proposals):
        # Proposal factor: if there is more than one proposal ending in the same epoch,
        # the resulting slot is divided by the req_amounts of them.
        # This is set in the function dt_parser_utils.get_valid_ending_proposals.

        # ending_proposals = [p for p in pst.valid_proposals.values() if p.end_epoch == proposal_state.end_epoch]

        if pst.debug: print("Ending proposals in the same epoch than the one referenced here:", ending_proposals)

        if len(ending_proposals) > 1:
            total_req_amount = sum([p.req_amount for p in ending_proposals])
            self.dist_factor = Decimal(self.req_amount) / total_req_amount
        else:
            self.dist_factor = Decimal(1)

        if pst.debug: print("Dist factor", self.dist_factor)


    def validate_priority(self, stx, dist_round):
        """Validates the priority of signalling transactions in round 2, 3, 5 and 6."""

        if dist_round in (0, 3, 6, 7):
            return True # rounds without priority check

        elif dist_round == 4: # rd 5 is special because all donors of previous rounds are admitted.
            valid_rounds = (0, 1, 2, 3)

        else:
            valid_rounds = (dist_round - 1)

        for rd in valid_rounds:
            # idea: check if address in stx is found in donation txes of previous rounds.
            for dtx in self.donation_txes[rd]:
                if stx.address == dtx.reserve_address:
                    # was slot filled?
                    # TODO: check how this works with ProposalModifications which increase req_amount.
                    if dtx.amount >= get_slot(dtx, self.req_amount, total_amount=self.signalled_amounts[rd], dist_round=rd):
                        return True
        return False

    def validate_timelock(self, dtx, dist_round):
        """Checks that the timelock of the donation is correct."""
        if dist_round > 3:
            return True
        # Timelock must be set at least to the block height of the start of round 5.
        elif dtx.timelock >= self.round_starts[4]:
            return True
        else:
            return False
        
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


class DonationHashLockScript(Hashlock256Script):
    def __init__(self, locking_hash, dest_address, network=PeercoinTestnet):
        """first arg: hash, second arg: locked script. """
        dest_address = Address.from_string(dest_address_string, network=network)
        locked_script = P2pkhScript(dest_address)
        super().__init__(locking_hash, locked_script)



class DonationHTLC(IfElseScript):
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

    

   

