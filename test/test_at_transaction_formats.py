import pytest
import pypeerassets.at.transaction_formats as tf

# maximum length of the formats is 76 bytes.
LONGSTRING = "abcdefghijklmnopqrstuvxyzABCDEFGHIJKLMNOPQRSTUVXYZ1234567890äëïöüáéíóú+-!$%&"

def test_getfmt_proposal():
  strvar = LONGSTRING
  fmt = tf.PROPOSAL_FORMAT
  key = "sla"
  result = tf.getfmt(strvar, fmt, key)
  assert result == "LM" # LONGSTRING[36:38]

def test_getfmt_donation():
  strvar = LONGSTRING
  fmt = tf.DONATION_FORMAT
  key = "prp"
  result = tf.getfmt(strvar, fmt, key)
  assert result == "cdefghijklmnopqrstuvxyzABCDEFGHI" # LONGSTRING[2:34]

def test_getfmt_locking():
  strvar = LONGSTRING
  fmt = tf.LOCKING_FORMAT
  key = "prp" 
  result = tf.getfmt(strvar, fmt, key)
  assert result == "cdefghijklmnopqrstuvxyzABCDEFGHI" # LONGSTRING[2:34]

def test_getfmt_signalling():
  strvar = LONGSTRING
  fmt = tf.SIGNALLING_FORMAT
  key = "id" 
  result = tf.getfmt(strvar, fmt, key)
  assert result == "ab" # LONGSTRING[0:2]

def test_getfmt_voting():
  strvar = LONGSTRING
  fmt = tf.VOTING_FORMAT
  key = "vot" 
  result = tf.getfmt(strvar, fmt, key)
  assert result == "J" # LONGSTRING[34]

def test_getfmt_at_deck_spawn():
  strvar = LONGSTRING
  fmt = tf.DECK_SPAWN_AT_FORMAT
  key = "adr"
  result = tf.getfmt(strvar, fmt, key)
  assert result == "efghijklmnopqrstuvxyzABCDEFGHIJKLMNOPQRSTUVXYZ1234567890äëïöüáéíóú+-!$%&" # LONGSTRING[4:]

def test_getfmt_dt_deck_spawn():
  strvar = LONGSTRING
  fmt = tf.DECK_SPAWN_DT_FORMAT
  key = "sdq"
  result = tf.getfmt(strvar, fmt, key)
  assert result == "i" # LONGSTRING[8]

def test_getfmt_at_cardissue():
  strvar = LONGSTRING
  fmt = tf.CARD_ISSUE_AT_FORMAT
  key = "out"
  result = tf.getfmt(strvar, fmt, key)
  assert result == 'J' # LONGSTRING[34]

def test_getfmt_dt_cardissue():
  strvar = LONGSTRING
  fmt = tf.CARD_ISSUE_DT_FORMAT
  key = "dtx"
  result = tf.getfmt(strvar, fmt, key)
  assert result == "cdefghijklmnopqrstuvxyzABCDEFGHI" # LONGSTRING[2:34]



