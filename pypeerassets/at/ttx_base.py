from btcpy.structs.address import P2pkhAddress
from btcpy.structs.crypto import PublicKey
from btcpy.structs.script import NulldataScript, UnknownScript, StackData

from pypeerassets.transactions import Transaction, TxIn, TxOut, Locktime
from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import parse_protobuf

DATASTR_OUTPUT = 1

class BaseTrackedTransaction(Transaction):
    """Base Tracked Transaction class, offering basic methods for all extensions which use TrackedTransactions.
       (DT, AT, DEX)"""


    def __init__(self, deck, provider=None, txid=None, version=None, ins=[], outs=[], locktime=0, network=None, timestamp=None, blockhash=None):

        object.__setattr__(self, 'version', version)
        object.__setattr__(self, 'ins', tuple(ins))
        object.__setattr__(self, 'outs', tuple(outs))
        object.__setattr__(self, 'locktime', locktime)
        object.__setattr__(self, '_txid', txid)
        object.__setattr__(self, 'network', network)
        object.__setattr__(self, 'timestamp', timestamp)

        object.__setattr__(self, 'input_addresses', self.set_input_addresses(provider=provider))

        blockseq = None

        # The blockheight parameter has always to come from blockhash
        # this ensures no unconfirmed transaction can slip through,
        # even if not called with .from_json constructor
        try:
            block = provider.getblock(blockhash)
            blockheight = block["height"]
            blockseq = block["tx"].index(txid)
        except (KeyError, TypeError):
            blockheight, blockseq = None, None # unconfirmed transaction

        object.__setattr__(self, 'blockheight', blockheight)
        object.__setattr__(self, 'blockseq', blockseq)

        # Inputs and outputs must always be provided by constructors.

        if len(ins) == 0 or len(outs) < 3:
            raise InvalidTrackedTransactionError("Creating a TrackedTransaction you must provide at least 3 outputs.")

        # other attributes come from datastr
        # CONVENTION: datastr is always in SECOND output (outs[1]) like in PeerAssets tx.

        try:
            scriptpubkey = self.outs[DATASTR_OUTPUT].script_pubkey
            # btcpy doesn't automatically create a NulldataScript of the sitze is over 83 bytes.
            if type(scriptpubkey) == NulldataScript:
                datastr = bytes(scriptpubkey.data.data)
            elif type(scriptpubkey) == UnknownScript:
                datastr = scriptpubkey.body[3:] # this is a bit of a hack, but btcpy is very unflexible here.


        except Exception as e: # if no op_return it throws InvalidNulldataOutput

            print("ERROR", e)
            raise InvalidTrackedTransactionError("No OP_RETURN data.")

        try:
            object.__setattr__(self, 'metadata', parse_protobuf(datastr, "ttx"))

        except Exception as e:
            print("Error, metadata not correctly formatted for protobuf.")
            print(e)
        object.__setattr__(self, 'deck', deck)
        object.__setattr__(self, 'ttx_version', self.metadata["version"])


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

        return '{}({})'.format(type(self).__name__, ", ".join(strlist))


    @property
    def txid(self):
        return self._txid

    @property
    def deckid(self):
        return self.deck.id # self.deck always comes from the ParserState.

    @classmethod
    def get_basicdata(cls, txid, provider):
        json = provider.getrawtransaction(txid, True)
        try:
            import pypeerassets.pautils as pu
            data = pu.read_tx_opreturn(json["vout"][1])
        except KeyError:
            raise InvalidTrackedTransactionError("JSON output:", json)
        return {"data" : data, "json" : json}

    @classmethod
    def from_json(cls, tx_json, provider, deck=None):
        network = net_query(provider.network)
        try:

            return cls(
                deck=deck,
                provider=provider,
                version=tx_json['version'],
                ins=[TxIn.from_json(txin_json) for txin_json in tx_json['vin']],
                outs=[TxOut.from_json(txout_json, network=network) for txout_json in tx_json['vout']],
                locktime=Locktime(tx_json['locktime']),
                txid=tx_json['txid'],
                network=network,
                timestamp=tx_json['time'],
                blockhash=tx_json['blockhash'],
            )

        except (KeyError, IndexError, ValueError):
            raise InvalidTrackedTransactionError("Transaction without correct datastring or unconfirmed transaction.")


    @classmethod
    def from_txid(cls, txid, provider, deck=None, basicdata=None):

        if basicdata is None:
           basicdata = cls.get_basicdata(txid, provider)

        return cls.from_json(basicdata["json"], provider=provider, deck=deck)

    def coin_multiplier(self):

        network_params = self.network # net_query(self.network.shortname)

        return int(1 / network_params.from_unit) # perhaps to_unit can be used without the division

    def get_input_address(self, pubkey_hexstr):
        # calculates input address from pubkey from scriptsig.

        pubkey = PublicKey(bytearray.fromhex(pubkey_hexstr))
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


class InvalidTrackedTransactionError(ValueError):
    # raised anytime when a (Base)TrackedTransaction is not following the intended format.
    pass
