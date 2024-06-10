
'''Communicate with local or remote peercoin-daemon via JSON-RPC'''

from operator import itemgetter
from .common import Provider
from pypeerassets.exceptions import InsufficientFunds
from btcpy.structs.transaction import MutableTxIn, Sequence, ScriptSig
from decimal import Decimal, getcontext, localcontext ### localcontext added for more precise utxo value calculation
getcontext().prec = 15  # precision for Decimal, to avoid rounding errors

try:
    from peercoin_rpc import Client
except ImportError:
    raise ImportError("peercoin_rpc library is required for this to work,\
                       use the pip to install it.")


class RpcNode(Client, Provider):
    '''JSON-RPC connection to local Peercoin node'''

    def select_inputs(self, address: str, amount: Decimal) -> dict:
        '''finds apropriate utxo's to include in rawtx, while being careful
        to never spend old transactions with a lot of coin age.
        Argument is intiger, returns list of apropriate UTXO's'''
        ### BUGFIX: changed amount from int to Decimal. ###

        utxos = []
        utxo_sum = Decimal(0)
        for tx in sorted(self.listunspent(address=address), key=itemgetter('confirmations')):

            if tx["address"] not in (self.pa_parameters.P2TH_addr,
                                     self.pa_parameters.test_P2TH_addr):

                utxos.append(
                        MutableTxIn(txid=tx['txid'],
                                    txout=tx['vout'],
                                    sequence=Sequence.max(),
                                    script_sig=ScriptSig.empty())
                         )


                utxo_sum += Decimal(str(tx["amount"]))
                if utxo_sum >= amount:
                    return {'utxos': utxos, 'total': utxo_sum}

        if utxo_sum < amount:
            raise InsufficientFunds("Insufficient funds.")

        raise Exception("undefined behavior :.(")

    @property
    def is_testnet(self) -> bool:
        '''check if node is configured to use testnet or mainnet'''

        if self.getblockchaininfo().get("chain") == "test":
            return True
        else:
            return False

    @property
    def network(self) -> str:
        '''return which network is the node operating on.'''

        if self.is_testnet:
            return "tppc"
        else:
            return "ppc"

    def listunspent(
        self,
        address: str="",
        minconf: int=1,
        maxconf: int=999999,
    ) -> list:
        '''list UTXOs
        modified version to allow filtering by address.
        '''
        if address:
            return self.req("listunspent", [minconf, maxconf, [address]])

        return self.req("listunspent", [minconf, maxconf])

    def getbalance_old(self, address): ### NEW FEATURE, because getbalance doesn't work with addresses in rpcnode. ###
        '''wrapper, because there is no address balance feature for rpcnode.
           Seems to work, but it's possible that not all addresses can be shown.'''
        groups = self.req("listaddressgroupings")
        for g in groups:
            for entry in g:
                if entry[0] == address:
                    return entry[1]
        else:
            raise Exception("Address not found in wallet managed by the RPC node. Import it there or use another provider.")

    def getbalance(self, address): ### version 2. Uses listunspent (faster) and does not reject empty addresses ###
        unspent = self.listunspent(address=address)
        values = [ Decimal(v["amount"]) for v in unspent ]
        return sum(values)


    def listtransactions(self, account="", many=999, since=0, include_watchonly=True): ### NEW FEATURE ###
        return self.req("listtransactions", [account, many, since, include_watchonly])

    def getblockchaininfo(self): ### NEW FEATURE ###
        return self.req("getblockchaininfo")

    def rescanblockchain(self): ### NEW FEATURES ###
        return self.req("rescanblockchain")

    def importaddress(self, address, label=None, rescan=False, p2sh=False): ### NEW FEATURE ###
        return self.req("importaddress", [address, label, rescan, p2sh])

    def setaccount(self, address, account): ### NEW FEATURE ###
        return self.req("setaccount", [address, account])

    def getblock(self, blockhash, decode=True): ### NEW: overrides getblock because the original expects a decode (boolean) value, otherwise doesn't work as expected. This is a bug in the Peerassets original code.
        return self.req("getblock", [blockhash, decode])

