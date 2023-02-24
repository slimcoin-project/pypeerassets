# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: trackedtransaction-specification.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='trackedtransaction-specification.proto',
  package='',
  syntax='proto3',
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n&trackedtransaction-specification.proto\"\xc4\x01\n\x12TrackedTransaction\x12\x0f\n\x07version\x18\x01 \x01(\r\x12\n\n\x02id\x18\x02 \x01(\x0c\x12\x0c\n\x04txid\x18\x03 \x01(\x0c\x12\x0e\n\x06\x65pochs\x18\x04 \x01(\r\x12\x0b\n\x03sla\x18\x05 \x01(\r\x12\x0e\n\x06\x61mount\x18\x06 \x01(\x04\x12\x10\n\x08locktime\x18\x07 \x01(\r\x12\x10\n\x08lockhash\x18\x08 \x01(\x0c\x12\x15\n\rlockhash_type\x18\t \x01(\r\x12\x0c\n\x04vote\x18\n \x01(\x08\x12\r\n\x05txid2\x18\x11 \x01(\x0c\".\n\x10\x43\x61rdExtendedData\x12\x0c\n\x04txid\x18\x01 \x01(\x0c\x12\x0c\n\x04vout\x18\x02 \x01(\r\"\xbe\x01\n\x10\x44\x65\x63kExtendedData\x12\n\n\x02id\x18\x01 \x01(\x0c\x12\x11\n\tepoch_len\x18\x02 \x01(\r\x12\x0e\n\x06reward\x18\x03 \x01(\r\x12\x10\n\x08min_vote\x18\x04 \x01(\r\x12\x17\n\x0fspecial_periods\x18\x05 \x01(\r\x12\x1b\n\x13voting_token_deckid\x18\x06 \x01(\x0c\x12\x12\n\nmultiplier\x18\x07 \x01(\r\x12\x0c\n\x04hash\x18\x08 \x01(\x0c\x12\x11\n\thash_type\x18\t \x01(\rb\x06proto3'
)




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
      number=2, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
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
      name='sla', full_name='TrackedTransaction.sla', index=4,
      number=5, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='amount', full_name='TrackedTransaction.amount', index=5,
      number=6, type=4, cpp_type=4, label=1,
      has_default_value=False, default_value=0,
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
    _descriptor.FieldDescriptor(
      name='txid2', full_name='TrackedTransaction.txid2', index=10,
      number=17, type=12, cpp_type=9, label=1,
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
  serialized_start=43,
  serialized_end=239,
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
    _descriptor.FieldDescriptor(
      name='vout', full_name='CardExtendedData.vout', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
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
  serialized_start=241,
  serialized_end=287,
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
      name='id', full_name='DeckExtendedData.id', index=0,
      number=1, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='epoch_len', full_name='DeckExtendedData.epoch_len', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='reward', full_name='DeckExtendedData.reward', index=2,
      number=3, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='min_vote', full_name='DeckExtendedData.min_vote', index=3,
      number=4, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='special_periods', full_name='DeckExtendedData.special_periods', index=4,
      number=5, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='voting_token_deckid', full_name='DeckExtendedData.voting_token_deckid', index=5,
      number=6, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='multiplier', full_name='DeckExtendedData.multiplier', index=6,
      number=7, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='hash', full_name='DeckExtendedData.hash', index=7,
      number=8, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='hash_type', full_name='DeckExtendedData.hash_type', index=8,
      number=9, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
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
  serialized_start=290,
  serialized_end=480,
)

DESCRIPTOR.message_types_by_name['TrackedTransaction'] = _TRACKEDTRANSACTION
DESCRIPTOR.message_types_by_name['CardExtendedData'] = _CARDEXTENDEDDATA
DESCRIPTOR.message_types_by_name['DeckExtendedData'] = _DECKEXTENDEDDATA
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

TrackedTransaction = _reflection.GeneratedProtocolMessageType('TrackedTransaction', (_message.Message,), {
  'DESCRIPTOR' : _TRACKEDTRANSACTION,
  '__module__' : 'trackedtransaction_specification_pb2'
  # @@protoc_insertion_point(class_scope:TrackedTransaction)
  })
_sym_db.RegisterMessage(TrackedTransaction)

CardExtendedData = _reflection.GeneratedProtocolMessageType('CardExtendedData', (_message.Message,), {
  'DESCRIPTOR' : _CARDEXTENDEDDATA,
  '__module__' : 'trackedtransaction_specification_pb2'
  # @@protoc_insertion_point(class_scope:CardExtendedData)
  })
_sym_db.RegisterMessage(CardExtendedData)

DeckExtendedData = _reflection.GeneratedProtocolMessageType('DeckExtendedData', (_message.Message,), {
  'DESCRIPTOR' : _DECKEXTENDEDDATA,
  '__module__' : 'trackedtransaction_specification_pb2'
  # @@protoc_insertion_point(class_scope:DeckExtendedData)
  })
_sym_db.RegisterMessage(DeckExtendedData)


# @@protoc_insertion_point(module_scope)
