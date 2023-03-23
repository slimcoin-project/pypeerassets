import pypeerassets.transactions as patx # MutableTransaction, tx_output, p2pkh_script, make_raw_transaction
from pypeerassets.provider import Provider
from decimal import Decimal
from pypeerassets.at.dt_misc_utils import coins_to_sats, sats_to_coins # these should be changed to here.
from pypeerassets.networks import net_query

class TransactionDraft():
    # the idea is to add inputs and outputs individually, not from the start,
    # and to have the Provider and the desired fee saved.
    # should later replace create_unsigned_tx in dt_misc_utils in a more "ordered" way.
    # all values will be able to be inputted in Decimal format.
    # TODO: it seems the PeerAssets classes are working almost all with Decimal instead of int,
    # maybe use Decimal for all atributes.

    def __init__(self, provider: Provider, ins: list=[], outs: list=[], fee_coins: Decimal=None, fee_sats: int=None, input_coins: Decimal=None, metadata: dict=None, extended_metadata: dict=None, change_output_index: int=None, debug: bool=False, locktime: int=0):

        self.provider = provider
        self.network = net_query(provider.network)
        self.ins = ins
        self.outs = outs

        self.define_fee(fee_sats, fee_coins) # TODO: solve problem for bigger txes than 1 kB

        self.metadata = metadata if metadata else {}
        self.ext_metadata = ext_metadata if extended_metadata else {} # this is for cases like asset_specific_Data
        if input_coins is not None:
            self.input_sats = self.coins_to_sats(input_value) # TODO there should be a way to calculate this without select_inputs.
        else:
            self.input_sats = 0
        self.change_output_index = change_output_index # to be able to reload / modify the change output.
        self.debug = debug
        self.locktime = locktime

    def define_fee(self, fee_sats: int=None, fee_coins: Decimal=None):
        if not fee_sats:
            if not fee_coins:
                fee_coins = self.network.min_tx_fee
            fee_sats = self.coins_to_sats(fee_coins)
        self.fee_sats = fee_sats


    def add_single_input(self, txid, vout):
        # needed for DEX, TODO!
        pass

    def add_necessary_inputs(self, input_address, coins=None, sats=None):
        # this searches for suitable inputs which fill the required amount (incl. tx fee)
        # amount can be specified or calculated automatically according to ins.
        if not (coins or sats):
            sats = self.get_required_amount()
        if sats:
            amount = self.sats_to_coins(sats)
        elif coins:
            amount = coins
        if self.debug:
            print("Input address and amount:", input_address, amount)
        input_query = self.provider.select_inputs(input_address, amount)
        inputs = input_query["utxos"]
        # print(inputs)
        input_sats = self.coins_to_sats(Decimal(input_query["total"]))
        self.ins += inputs
        self.input_sats += input_sats

    def add_p2pkh_output(self, address: str, coins: Decimal=None, sats: int=None, output_index: int=None, force: bool=False):

        if output_index is None:
            output_index = len(self.outs) # this gives an output 1 higher than the last.

        script = patx.p2pkh_script(address=address, network=self.provider.network)
        if coins:
            amount_coins = coins
        elif sats:
            amount_coins = self.sats_to_coins(sats)
        else:
            raise ValueError()

        new_output = patx.tx_output(network=self.network.shortname, value=amount_coins, n=output_index, script=script)

        if output_index == len(self.outs):
            self.outs.append(new_output)
        elif output_index < len(self.outs):
            if len(self.outs[output_index]) == 0 or force: # checks if output index is empty
                self.outs[output_index] = new_output
            # TODO: also here, an Exception could be raised.

    def add_opreturn_output(self, metadata):
        pass

    def add_change_output(self, address=None, force: bool=False, output_index=None):
        # creates output simply to change.
        # if address is None, a fresh address will be generated.
        if self.change_output_index:
            if force:
                self.outs[self.change_output_index] = None
                output_index = self.change_output_index # TODO: this only allows to recalc the same output_index.
            else:
                return
            #     raise ValueError("Change output already created!")  # maybe this would make sense. Decide later.

        if address is None:
            address = self.provider.getnewaddress() # TODO: there is an "account" param, add this.
        change_amount = self.input_sats - self.get_required_amount()
        if self.debug:
            print("Change amount:", change_amount)
        self.add_p2pkh_output(address, sats=change_amount, output_index=output_index)
        self.change_output_index = output_index


    def add_metadata_item(self):
        pass

    def get_required_amount(self):
        output_sum = sum([o.value for o in self.outs])
        fee = self.fee_sats
        if self.debug:
            print("output sum", output_sum)
            print("fee", fee)
        return output_sum + fee


    def to_raw_transaction(self):
        return patx.make_raw_transaction(network=self.provider.network,
                                       inputs=self.ins,
                                       outputs=self.outs,
                                       locktime=patx.Locktime(self.locktime)
                                       )

    def coin_value(self):
        return int(1 / self.network.from_unit)

    def sats_to_coins(self, sats: int) -> Decimal:
        return Decimal(sats) / self.coin_value()

    def coins_to_sats(self, coins: Decimal) -> int:
        return int(coins * self.coin_value())

    def min_p2th_fee(network) -> int:
        # this is a workaround.
        # normally, the minimal tx fee in PPC and derived coins is the same than the minimal amount for an output.
        # the correct way may be:
        # txout = network.tx_cls_out()
        # return txout.get_dust_threshold()
        return self.network.min_tx_fee



