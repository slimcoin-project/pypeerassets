from .rpcnode import RpcNode

# Slimcoin RPC node. As it's a subclass of RpcNode, it should be recognized as RpcNode by the isinstance checks
# in "vanilla" PeerAssets.

class SlmRpcNode(RpcNode):

    def userpass(self):
        return super().userpass(dir="slimcoin")

    @property
    def network(self) -> str:
        '''return which network is the node operating on.'''

        if self.is_testnet:
            return "tslm"
        else:
            return "slm"

    @property
    def is_testnet(self) -> bool:
        '''check if node is configured to use testnet or mainnet'''

        if (self.getblockchaininfo().get("chain") == "test") or (self.getinfo().get("testnet") == True): ### MODIFIED to allow 0.8+ and legacy clients
            return True
        else:
            return False


    def listtransactions(self, account="", many=999, since=0, fBurnTx=False):
        '''SLM has a different structure here. May also have to be extended to allow more than 999 transactions.'''
        return self.req("listtransactions", [account, fBurnTx, many, since])

        # [account="*"] [fBurnTx=false] [count=10] [from=0]

    def getblock(self, blockhash, decode=False, txinfo=False, txdetails=False):
        # SLM uses the old style getblock command without the decode parameter.
        # It is catched here so it's not passed to txinfo.
        block = self.req("getblock", [blockhash, txinfo, txdetails])
        # print(block)
        #for index, tx in enumerate(block["tx"]):
        #    block["tx"][index][0] = tx[0].replace(" base", "")
        #print(block)
        return block

    def importprivkey(self, wif, label, rescan=False):
        # SLM adds a rescan option
        return self.req("importprivkey", [wif, label, rescan])

    def getrawtransaction(self, txid, verbose=False):
        verbose_int = 1 if verbose else 0
        return self.req("getrawtransaction", [txid, verbose_int])

    def getburndata(self):
        return self.req("getburndata")

