# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: ttx_asd_specification_extradata.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='ttx_asd_specification_extradata.proto',
  package='',
  syntax='proto3',
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n%ttx_asd_specification_extradata.proto\"\x97\x02\n\x12TrackedTransaction\x12\x0f\n\x07version\x18\x01 \x01(\r\x12\n\n\x02id\x18\x02 \x01(\r\x12\x0c\n\x04txid\x18\x03 \x01(\x0c\x12\x0e\n\x06\x65pochs\x18\x04 \x01(\r\x12\x0e\n\x06\x61mount\x18\x05 \x01(\x04\x12\x13\n\x0b\x64\x65scription\x18\x06 \x01(\t\x12\x10\n\x08locktime\x18\x07 \x01(\r\x12\x10\n\x08lockhash\x18\x08 \x01(\x0c\x12\x15\n\rlockhash_type\x18\t \x01(\r\x12\x0c\n\x04vote\x18\n \x01(\x08\"X\n\x07TTXTYPE\x12\x08\n\x04NONE\x10\x00\x12\x0c\n\x08PROPOSAL\x10\x01\x12\n\n\x06VOTING\x10\x02\x12\x0e\n\nSIGNALLING\x10\x03\x12\x0b\n\x07LOCKING\x10\x04\x12\x0c\n\x08\x44ONATION\x10\x05\" \n\x10\x43\x61rdExtendedData\x12\x0c\n\x04txid\x18\x01 \x01(\x0c\"\xb2\x02\n\x10\x44\x65\x63kExtendedData\x12\x13\n\x0b\x65xt_version\x18\x01 \x01(\r\x12\n\n\x02id\x18\x02 \x01(\r\x12\x11\n\tepoch_len\x18\x03 \x01(\r\x12\x0e\n\x06reward\x18\x04 \x01(\r\x12\x10\n\x08min_vote\x18\x05 \x01(\r\x12\x17\n\x0fspecial_periods\x18\x06 \x01(\r\x12\x1b\n\x13voting_token_deckid\x18\x07 \x01(\x0c\x12\x12\n\nmultiplier\x18\x08 \x01(\r\x12\x0c\n\x04hash\x18\t \x01(\x0c\x12\x11\n\thash_type\x18\n \x01(\r\x12\x10\n\x08\x65ndblock\x18\x0b \x01(\r\x12\x12\n\nstartblock\x18\x0c \x01(\r\x12\x11\n\textradata\x18\r \x01(\x0c\"$\n\x08\x45XT_TYPE\x12\x08\n\x04NONE\x10\x00\x12\x06\n\x02\x41T\x10\x01\x12\x06\n\x02\x44T\x10\x02\x62\x06proto3'
)



_TRACKEDTRANSACTION_TTXTYPE = _descriptor.EnumDescriptor(
  name='TTXTYPE',
  full_name='TrackedTransaction.TTXTYPE',
  filename=None,
  file=DESCRIPTOR,
  create_key=_descriptor._internal_create_key,
  values=[
    _descriptor.EnumValueDescriptor(
      name='NONE', index=0, number=0,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='PROPOSAL', index=1, number=1,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='VOTING', index=2, number=2,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='SIGNALLING', index=3, number=3,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='LOCKING', index=4, number=4,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='DONATION', index=5, number=5,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=233,
  serialized_end=321,
)
_sym_db.RegisterEnumDescriptor(_TRACKEDTRANSACTION_TTXTYPE)

_DECKEXTENDEDDATA_EXT_TYPE = _descriptor.EnumDescriptor(
  name='EXT_TYPE',
  full_name='DeckExtendedData.EXT_TYPE',
  filename=None,
  file=DESCRIPTOR,
  create_key=_descriptor._internal_create_key,
  values=[
    _descriptor.EnumValueDescriptor(
      name='NONE', index=0, number=0,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='AT', index=1, number=1,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='DT', index=2, number=2,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=628,
  serialized_end=664,
)
_sym_db.RegisterEnumDescriptor(_DECKEXTENDEDDATA_EXT_TYPE)


_TRACKEDTRANSACTION = _descriptor.Descriptor(
  name='TrackedTransaction',
  full_name='TrackedTransaction',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='version', full_name='TrackedTransaction.version', index=0,
      number=1, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='id', full_name='TrackedTransaction.id', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='txid', full_name='TrackedTransaction.txid', index=2,
      number=3, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='epochs', full_name='TrackedTransaction.epochs', index=3,
      number=4, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='amount', full_name='TrackedTransaction.amount', index=4,
      number=5, type=4, cpp_type=4, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='description', full_name='TrackedTransaction.description', index=5,
      number=6, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=b"".decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='locktime', full_name='TrackedTransaction.locktime', index=6,
      number=7, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='lockhash', full_name='TrackedTransaction.lockhash', index=7,
      number=8, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='lockhash_type', full_name='TrackedTransaction.lockhash_type', index=8,
      number=9, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='vote', full_name='TrackedTransaction.vote', index=9,
      number=10, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _TRACKEDTRANSACTION_TTXTYPE,
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=42,
  serialized_end=321,
)


_CARDEXTENDEDDATA = _descriptor.Descriptor(
  name='CardExtendedData',
  full_name='CardExtendedData',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='txid', full_name='CardExtendedData.txid', index=0,
      number=1, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=323,
  serialized_end=355,
)


_DECKEXTENDEDDATA = _descriptor.Descriptor(
  name='DeckExtendedData',
  full_name='DeckExtendedData',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='ext_version', full_name='DeckExtendedData.ext_version', index=0,
      number=1, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='id', full_name='DeckExtendedData.id', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='epoch_len', full_name='DeckExtendedData.epoch_len', index=2,
      number=3, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='reward', full_name='DeckExtendedData.reward', index=3,
      number=4, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='min_vote', full_name='DeckExtendedData.min_vote', index=4,
      number=5, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='special_periods', full_name='DeckExtendedData.special_periods', index=5,
      number=6, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='voting_token_deckid', full_name='DeckExtendedData.voting_token_deckid', index=6,
      number=7, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='multiplier', full_name='DeckExtendedData.multiplier', index=7,
      number=8, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='hash', full_name='DeckExtendedData.hash', index=8,
      number=9, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='hash_type', full_name='DeckExtendedData.hash_type', index=9,
      number=10, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='endblock', full_name='DeckExtendedData.endblock', index=10,
      number=11, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='startblock', full_name='DeckExtendedData.startblock', index=11,
      number=12, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='extradata', full_name='DeckExtendedData.extradata', index=12,
      number=13, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _DECKEXTENDEDDATA_EXT_TYPE,
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=358,
  serialized_end=664,
)

_TRACKEDTRANSACTION_TTXTYPE.containing_type = _TRACKEDTRANSACTION
_DECKEXTENDEDDATA_EXT_TYPE.containing_type = _DECKEXTENDEDDATA
DESCRIPTOR.message_types_by_name['TrackedTransaction'] = _TRACKEDTRANSACTION
DESCRIPTOR.message_types_by_name['CardExtendedData'] = _CARDEXTENDEDDATA
DESCRIPTOR.message_types_by_name['DeckExtendedData'] = _DECKEXTENDEDDATA
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

TrackedTransaction = _reflection.GeneratedProtocolMessageType('TrackedTransaction', (_message.Message,), {
  'DESCRIPTOR' : _TRACKEDTRANSACTION,
  '__module__' : 'ttx_asd_specification_extradata_pb2'
  # @@protoc_insertion_point(class_scope:TrackedTransaction)
  })
_sym_db.RegisterMessage(TrackedTransaction)

CardExtendedData = _reflection.GeneratedProtocolMessageType('CardExtendedData', (_message.Message,), {
  'DESCRIPTOR' : _CARDEXTENDEDDATA,
  '__module__' : 'ttx_asd_specification_extradata_pb2'
  # @@protoc_insertion_point(class_scope:CardExtendedData)
  })
_sym_db.RegisterMessage(CardExtendedData)

DeckExtendedData = _reflection.GeneratedProtocolMessageType('DeckExtendedData', (_message.Message,), {
  'DESCRIPTOR' : _DECKEXTENDEDDATA,
  '__module__' : 'ttx_asd_specification_extradata_pb2'
  # @@protoc_insertion_point(class_scope:DeckExtendedData)
  })
_sym_db.RegisterMessage(DeckExtendedData)


# @@protoc_insertion_point(module_scope)
