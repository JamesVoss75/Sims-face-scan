# FaceScan bridge: Phase 1 proof-of-concept script mod for The Sims 4.
#
# STATUS: UNTESTED IN GAME.  Written against APIs confirmed in published mod
# code (sim_info.facial_attributes + protocolbuffers.PersistenceBlobs_pb2, see
# docs/01-sims4-face-system.md).  Run it only in a throwaway save; see
# mod/README.md for the experiment protocol.
#
# Cheat-console commands (live mode, active Sim):
#   facescan.dump              write the Sim's facial data to facescan/out/<sim_id>.json
#   facescan.set <key> <amt>   set one face modifier (key: hex SMOD id, amt: 0..1; 0 removes)
#   facescan.apply <file>      apply sculpts + face_modifiers from facescan/in/<file>
#   facescan.restore           restore the blob saved before the first change this session
#
# Must stay Python 3.7 compatible (the game's interpreter).
import json
import os

import services
import sims4.commands
from protocolbuffers import PersistenceBlobs_pb2

_backups = {}


def _root():
    # .../The Sims 4/Mods/<pkg>.ts4script/facescan_bridge.pyc -> .../The Sims 4/facescan
    path = os.path.abspath(__file__)
    while path and os.path.basename(path).lower() != "mods":
        parent = os.path.dirname(path)
        if parent == path:
            raise RuntimeError("could not locate the Mods folder from " + __file__)
        path = parent
    root = os.path.join(os.path.dirname(path), "facescan")
    for sub in ("in", "out"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root


def _active_sim_info():
    client = services.client_manager().get_first_client()
    return client.active_sim_info if client is not None else None


def _read_blob(sim_info):
    blob = PersistenceBlobs_pb2.BlobSimFacialCustomizationData()
    blob.ParseFromString(sim_info.facial_attributes)
    return blob


def _write_blob(sim_info, blob):
    if sim_info.sim_id not in _backups:
        _backups[sim_info.sim_id] = sim_info.facial_attributes
    sim_info.facial_attributes = blob.SerializeToString()


def _blob_to_json(blob):
    def mods(ms):
        return [{"key": "0x%016X" % m.key, "amount": m.amount} for m in ms]
    return {
        "sculpts": ["0x%016X" % s for s in blob.sculpts],
        "face_modifiers": mods(blob.face_modifiers),
        "body_modifiers": mods(blob.body_modifiers),
        "aged_face_modifiers": mods(blob.aged_face_modifiers),
        "aged_body_modifiers": mods(blob.aged_body_modifiers),
    }


def _set_face_modifier(blob, key, amount):
    for i in range(len(blob.face_modifiers) - 1, -1, -1):
        if blob.face_modifiers[i].key == key:
            del blob.face_modifiers[i]
    if amount:
        m = blob.face_modifiers.add()
        m.key = key
        m.amount = amount


def _with_sim(_connection, fn):
    out = sims4.commands.CheatOutput(_connection)
    try:
        sim_info = _active_sim_info()
        if sim_info is None:
            out("facescan: no active Sim")
            return
        out(fn(sim_info))
    except Exception as e:  # report everything to the console; never crash the game loop
        out("facescan error: %r" % (e,))


@sims4.commands.Command("facescan.dump", command_type=sims4.commands.CommandType.Live)
def facescan_dump(_connection=None):
    def run(sim_info):
        data = _blob_to_json(_read_blob(sim_info))
        data["sim_id"] = sim_info.sim_id
        data["age"] = str(sim_info.age)
        data["gender"] = str(sim_info.gender)
        path = os.path.join(_root(), "out", "%d.json" % sim_info.sim_id)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return "facescan: %d sculpts, %d face modifiers -> %s" % (
            len(data["sculpts"]), len(data["face_modifiers"]), path)
    _with_sim(_connection, run)


@sims4.commands.Command("facescan.set", command_type=sims4.commands.CommandType.Live)
def facescan_set(key: str = None, amount: float = 0.0, _connection=None):
    def run(sim_info):
        blob = _read_blob(sim_info)
        _set_face_modifier(blob, int(key, 16), float(amount))
        _write_blob(sim_info, blob)
        return "facescan: set %s = %s" % (key, amount)
    _with_sim(_connection, run)


@sims4.commands.Command("facescan.apply", command_type=sims4.commands.CommandType.Live)
def facescan_apply(filename: str = "face.json", _connection=None):
    def run(sim_info):
        with open(os.path.join(_root(), "in", os.path.basename(filename))) as f:
            data = json.load(f)
        blob = _read_blob(sim_info)
        if "sculpts" in data:
            del blob.sculpts[:]
            blob.sculpts.extend(int(s, 16) for s in data["sculpts"])
        if "face_modifiers" in data:
            del blob.face_modifiers[:]
            for m in data["face_modifiers"]:
                _set_face_modifier(blob, int(m["key"], 16), float(m["amount"]))
        _write_blob(sim_info, blob)
        return "facescan: applied %s" % filename
    _with_sim(_connection, run)


@sims4.commands.Command("facescan.restore", command_type=sims4.commands.CommandType.Live)
def facescan_restore(_connection=None):
    def run(sim_info):
        if sim_info.sim_id not in _backups:
            return "facescan: nothing to restore"
        sim_info.facial_attributes = _backups.pop(sim_info.sim_id)
        return "facescan: restored"
    _with_sim(_connection, run)
