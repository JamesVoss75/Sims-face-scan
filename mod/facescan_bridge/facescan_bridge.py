# FaceScan bridge: Phase 1 test mod for The Sims 4.
#
# STATUS: NOT YET RUN IN THE GAME.  Written against APIs seen in published mod
# code (sim_info.facial_attributes + protocolbuffers.PersistenceBlobs_pb2; see
# docs/01-sims4-face-system.md).  Use only with a disposable Sim in a
# disposable save; see docs/windows-testing.md.
#
# SAFETY: every command that changes a Sim refuses to run unless the active
# Sim's LAST NAME is "FaceScanTest".  Read-only commands work on any Sim.
#
# Cheat-console commands (live mode, acting on the active Sim):
#   facescan.info                      versions, paths, active Sim, write permission   (read-only)
#   facescan.dump                      facial data -> facescan/out/<sim_id>.json       (read-only)
#   facescan.validate_begin            apply the built-in test face, start a validation record
#   facescan.validate_check <label>    compare the current face with the expected one   (read-only)
#   facescan.validate_restore          put back the face from before validate_begin
#   facescan.set <hexkey> <amount>     set one face modifier (0 removes it)
#   facescan.apply <file>              apply facescan/in/<file> (sculpts + face_modifiers)
#
# Must stay Python 3.7 compatible (the game's interpreter).
import binascii
import json
import os
import struct
import sys
import time

import services
import sims4.commands
from protocolbuffers import PersistenceBlobs_pb2

MOD_VERSION = "0.2.0"
REQUIRED_LAST_NAME = "facescantest"
LISTS = ("face_modifiers", "body_modifiers", "aged_face_modifiers", "aged_body_modifiers")

# Built-in test face for teen/young adult/adult/elder humans.  These ages use
# the "yfhead" modifier names in EA's CAS modifier tuning.  Odd values make
# rounding or snapping visible.  "core" entries must survive every step.
# "probe" entries test edge behaviour: Eyes_Big is above its CAS drag limit
# (LimitDirectManip 0.52 for YA), and Chin_Wide has no tuning entry.  Changes
# to probes are recorded as observations, not failures.
TEST_FACE = (
    ("yfheadNose_Wide", 0.613, "core"),
    ("yfheadMouth_Wide", 0.271, "core"),
    ("yfheadChin_Forward", 0.437, "core"),
    ("yfheadEyes_Big", 0.800, "probe"),
    ("yfheadChin_Wide", 0.500, "probe"),
)
OPPOSITES = ("yfheadNose_Narrow", "yfheadMouth_Narrow", "yfheadChin_Backward",
             "yfheadEyes_Small", "yfheadChin_Narrow")
BLOCKED_AGES = ("BABY", "INFANT", "TODDLER", "CHILD")

_backups = {}


def fnv64(name):
    h = 0xCBF29CE484222325
    for b in name.lower().encode("ascii"):
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        h ^= b
    return h


def _root():
    # .../The Sims 4/Mods/<file>.ts4script/facescan_bridge.pyc -> .../The Sims 4/facescan
    path = os.path.abspath(__file__)
    while os.path.basename(path).lower() != "mods":
        parent = os.path.dirname(path)
        if parent == path:
            raise RuntimeError("could not locate the Mods folder from " + __file__)
        path = parent
    root = os.path.join(os.path.dirname(path), "facescan")
    for sub in ("in", "out", "validation"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root


def _active_sim_info():
    client = services.client_manager().get_first_client()
    return client.active_sim_info if client is not None else None


def _sim_label(sim_info):
    return "%s %s (id %d, %s, %s)" % (sim_info.first_name, sim_info.last_name, sim_info.sim_id,
                                      sim_info.age, sim_info.gender)


def _write_allowed(sim_info):
    if (sim_info.last_name or "").strip().lower() != REQUIRED_LAST_NAME:
        return "refused: the active Sim's last name must be FaceScanTest (disposable test Sim)"
    if any(a in str(sim_info.age).upper() for a in BLOCKED_AGES):
        return "refused: test face is defined for teen..elder only (age %s)" % sim_info.age
    species = str(getattr(sim_info, "species", "HUMAN")).upper()
    if "HUMAN" not in species:
        return "refused: humans only (species %s)" % species
    return None


def _parse(raw):
    blob = PersistenceBlobs_pb2.BlobSimFacialCustomizationData()
    blob.ParseFromString(raw)
    return blob


def _hex(raw):
    return binascii.hexlify(raw).decode("ascii")


def _blob_to_json(blob):
    def mods(ms):
        return [{"key": "0x%016X" % m.key, "amount": m.amount} for m in ms]
    d = {"sculpts": ["0x%016X" % s for s in blob.sculpts]}
    for name in LISTS:
        d[name] = mods(getattr(blob, name))
    return d


def _set_face_modifier(blob, key, amount):
    for i in range(len(blob.face_modifiers) - 1, -1, -1):
        if blob.face_modifiers[i].key == key:
            del blob.face_modifiers[i]
    if amount:
        m = blob.face_modifiers.add()
        m.key = key
        m.amount = amount


def _write_blob(sim_info, raw):
    if sim_info.sim_id not in _backups:
        _backups[sim_info.sim_id] = sim_info.facial_attributes
    sim_info.facial_attributes = raw


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _compare(expected_raw, actual_raw, probe_keys):
    """Return (core_problems, probe_observations)."""
    exp, act = _parse(expected_raw), _parse(actual_raw)
    core, probe = [], []
    if sorted(exp.sculpts) != sorted(act.sculpts):
        core.append("sculpts differ: expected %s, got %s" % (
            ["0x%016X" % s for s in exp.sculpts], ["0x%016X" % s for s in act.sculpts]))
    for name in LISTS:
        e = dict((m.key, m.amount) for m in getattr(exp, name))
        a = dict((m.key, m.amount) for m in getattr(act, name))
        for k in sorted(set(e) | set(a)):
            if k not in a:
                msg = "%s 0x%016X missing (expected %.6f)" % (name, k, e[k])
            elif k not in e:
                msg = "%s 0x%016X unexpected (= %.6f)" % (name, k, a[k])
            elif abs(_f32(e[k]) - _f32(a[k])) > 1e-6:
                msg = "%s 0x%016X %.6f -> %.6f" % (name, k, e[k], a[k])
            else:
                continue
            (probe if k in probe_keys else core).append(msg)
    return core, probe


def _record_path(sim_info):
    return os.path.join(_root(), "validation", "%d.json" % sim_info.sim_id)


def _run(_connection, fn, needs_write):
    out = sims4.commands.CheatOutput(_connection)
    try:
        sim_info = _active_sim_info()
        if sim_info is None:
            out("facescan: no active Sim")
            return
        if needs_write:
            refusal = _write_allowed(sim_info)
            if refusal:
                out("facescan: " + refusal)
                return
        for line in fn(sim_info).split("\n"):
            out(line)
    except Exception as e:  # report to the console; never let an error escape into the game loop
        out("facescan error: %r" % (e,))


@sims4.commands.Command("facescan.info", command_type=sims4.commands.CommandType.Live)
def facescan_info(_connection=None):
    def run(sim_info):
        refusal = _write_allowed(sim_info)
        return "\n".join([
            "facescan %s, python %s" % (MOD_VERSION, sys.version.split()[0]),
            "loaded from %s" % __file__,
            "data folder %s" % _root(),
            "active Sim: %s, species %s" % (_sim_label(sim_info), getattr(sim_info, "species", "?")),
            "writes: " + ("allowed" if refusal is None else refusal),
        ])
    _run(_connection, run, needs_write=False)


@sims4.commands.Command("facescan.dump", command_type=sims4.commands.CommandType.Live)
def facescan_dump(_connection=None):
    def run(sim_info):
        raw = sim_info.facial_attributes
        data = _blob_to_json(_parse(raw))
        data.update({"sim_id": sim_info.sim_id, "first_name": sim_info.first_name,
                     "last_name": sim_info.last_name, "age": str(sim_info.age),
                     "gender": str(sim_info.gender), "blob_hex": _hex(raw),
                     "mod_version": MOD_VERSION, "time": time.time()})
        path = os.path.join(_root(), "out", "%d.json" % sim_info.sim_id)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return "facescan: %d sculpts, %d face modifiers -> %s" % (
            len(data["sculpts"]), len(data["face_modifiers"]), path)
    _run(_connection, run, needs_write=False)


@sims4.commands.Command("facescan.validate_begin", command_type=sims4.commands.CommandType.Live)
def facescan_validate_begin(_connection=None):
    def run(sim_info):
        baseline = sim_info.facial_attributes
        blob = _parse(baseline)
        for name in OPPOSITES:
            _set_face_modifier(blob, fnv64(name), 0.0)
        for name, amount, _role in TEST_FACE:
            _set_face_modifier(blob, fnv64(name), amount)
        expected = blob.SerializeToString()
        _write_blob(sim_info, expected)
        written = sim_info.facial_attributes
        record = {
            "format": "facescan-validation/1", "mod_version": MOD_VERSION,
            "python": sys.version.split()[0], "sim_id": sim_info.sim_id,
            "sim": _sim_label(sim_info), "started": time.time(),
            "baseline_hex": _hex(baseline), "expected_hex": _hex(expected),
            "test_face": [{"name": n, "key": "0x%016X" % fnv64(n), "amount": a, "role": r}
                          for n, a, r in TEST_FACE],
            "removed": [{"name": n, "key": "0x%016X" % fnv64(n)} for n in OPPOSITES],
            "checkpoints": [],
        }
        with open(_record_path(sim_info), "w") as f:
            json.dump(record, f, indent=2)
        same = "identical" if written == expected else "DIFFERENT (%d vs %d bytes)" % (len(written), len(expected))
        return ("facescan: test face applied; read-back is %s\n"
                "next: look at the Sim's face, then run facescan.validate_check live_applied" % same)
    _run(_connection, run, needs_write=True)


@sims4.commands.Command("facescan.validate_check", command_type=sims4.commands.CommandType.Live)
def facescan_validate_check(label="check", _connection=None):
    def run(sim_info):
        path = _record_path(sim_info)
        if not os.path.exists(path):
            return "facescan: no validation record for this Sim; run facescan.validate_begin first"
        with open(path) as f:
            record = json.load(f)
        probes = set(fnv64(t["name"]) for t in record["test_face"] if t["role"] == "probe")
        actual = sim_info.facial_attributes
        core, probe = _compare(binascii.unhexlify(record["expected_hex"]), actual, probes)
        result = "PASS" if not core else "FAIL"
        record["checkpoints"].append({"label": label, "time": time.time(), "result": result,
                                      "blob_hex": _hex(actual), "core_problems": core,
                                      "probe_observations": probe})
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        lines = ["facescan: checkpoint %s: %s (%d problems, %d probe changes)" % (label, result, len(core), len(probe))]
        lines += ["  " + p for p in (core + probe)[:8]]
        return "\n".join(lines)
    _run(_connection, run, needs_write=False)


@sims4.commands.Command("facescan.validate_restore", command_type=sims4.commands.CommandType.Live)
def facescan_validate_restore(_connection=None):
    def run(sim_info):
        path = _record_path(sim_info)
        if not os.path.exists(path):
            return "facescan: no validation record for this Sim"
        with open(path) as f:
            record = json.load(f)
        sim_info.facial_attributes = binascii.unhexlify(record["baseline_hex"])
        return "facescan: baseline face restored"
    _run(_connection, run, needs_write=True)


@sims4.commands.Command("facescan.set", command_type=sims4.commands.CommandType.Live)
def facescan_set(key=None, amount="0", _connection=None):
    def run(sim_info):
        if key is None:
            return "usage: facescan.set <hexkey> <amount>"
        blob = _parse(sim_info.facial_attributes)
        _set_face_modifier(blob, int(key, 16), float(amount))
        _write_blob(sim_info, blob.SerializeToString())
        return "facescan: set %s = %s" % (key, amount)
    _run(_connection, run, needs_write=True)


@sims4.commands.Command("facescan.apply", command_type=sims4.commands.CommandType.Live)
def facescan_apply(filename="face.json", _connection=None):
    def run(sim_info):
        with open(os.path.join(_root(), "in", os.path.basename(filename))) as f:
            data = json.load(f)
        blob = _parse(sim_info.facial_attributes)
        if "sculpts" in data:
            del blob.sculpts[:]
            blob.sculpts.extend(int(s, 16) for s in data["sculpts"])
        if "face_modifiers" in data:
            del blob.face_modifiers[:]
            for m in data["face_modifiers"]:
                _set_face_modifier(blob, int(m["key"], 16), float(m["amount"]))
        _write_blob(sim_info, blob.SerializeToString())
        return "facescan: applied %s" % filename
    _run(_connection, run, needs_write=True)
