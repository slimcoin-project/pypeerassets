import pytest
import pypeerassets.at.dt_slots as sl
from decimal import Decimal
from .at_dt_dummy_classes import TestObj

COIN=100000000
CENT=1000000

def test_get_raw_slot():
    tx_amount = 20
    total_amount = 200
    # req_amount = 100 # not necessary in this test
    slot_rest = 30
    slot = sl.get_raw_slot(tx_amount, av_amount=slot_rest, total_amount=total_amount)
    assert slot == 3

@pytest.mark.parametrize("slot_rest", [50, 100, 200])
def test_get_first_serve_slot(slot_rest):
    stx = TestObj(txid="e", amount=20)
    fake_tx1 = TestObj(txid="a", amount=40)
    fake_tx2 = TestObj(txid="b", amount=50)
    fake_tx3 = TestObj(txid="c", amount=20)
    fake_tx4 = TestObj(txid="d", amount=60)
    round_txes = [fake_tx1, fake_tx2, stx, fake_tx3, fake_tx4]

    slot = sl.get_first_serve_slot(stx, round_txes, slot_rest=slot_rest)
    if slot_rest == 50:
        assert slot == 0
    elif slot_rest == 100:
        assert slot == 10
    else:
        assert slot == 20

@pytest.mark.parametrize("av_amount", [100*COIN, 200*COIN, 5010*CENT])
def test_get_priority_slot(av_amount):
    #stx_amounts = [5, 7, 10, 2, 0.5] # 24.5 (+ 20 from tx = 44.5)
    #rtx_amounts = [25, 11.2, 56] # 92.2
    tx = TestObj(amount=20*COIN, txid="x")
    stxes = [TestObj(amount=5*COIN, txid="a"), TestObj(amount=7*COIN, txid="b"), TestObj(amount=10*COIN, txid="c"), TestObj(amount=2*COIN, txid="d"), TestObj(amount=50*CENT, txid="e"), tx]
    rtxes = [TestObj(reserved_amount=25*COIN, txid="1"), TestObj(reserved_amount=1120*CENT, txid="2"), TestObj(reserved_amount=56*COIN, txid="3")]
    #stxes = [TestObj(amount=int(a*COIN)) for a in stx_amounts]
    #rtxes = [TestObj(reserved_amount=int(a*COIN)) for a in rtx_amounts]
    slot = sl.get_priority_slot(tx, rtxes, stxes, av_amount, ramount=None, samount=None)
    if av_amount == 100*COIN:
        assert slot == 350561797 # rest of 7.8 is divided by 44.5, * 20
    elif av_amount == 200*COIN:
        assert slot == 20 * COIN # complete slot
    elif av_amount == 50*COIN:
        assert slot == 0 # slot only for rtxes





