# FaceScan bridge: Phase 1 test mod for The Sims 4.
#
# STATUS: NOT YET RUN IN THE GAME.  Written against APIs seen in published mod
# code (sim_info.facial_attributes + protocolbuffers.PersistenceBlobs_pb2; see
# docs/01-sims4-face-system.md).  Use only with a disposable Sim in a
# disposable save; see docs/windows-testing.md.
#
# SAFETY: every command that changes a Sim refuses to run unless the active
# Sim's LAST NAME is "FaceScanTest".  Read-only commands work on any Sim.
# Nothing runs in the background: the mod only acts when a command is typed.
#
# DIAGNOSTICS (all under Documents/Electronic Arts/The Sims 4/facescan/):
#   mod_loaded.json     written when the game loads the mod (proves it loaded)
#   facescan_log.txt    every command, its result, and full tracebacks on errors
#   out/api_probe.json  attribute names available on the live sim_info (facescan.info)
#
# Cheat-console commands (live mode, acting on the active Sim):
#   facescan.step                      guided test: run it repeatedly, it says what to do next
#   facescan.undo                      put back the face from before the test, close the test
#   facescan.info                      versions, paths, active Sim, write permission   (read-only)
#   facescan.dump                      facial data -> facescan/out/<sim_id>.json       (read-only)
#   facescan.validate_begin / facescan.validate_check <label> / facescan.validate_restore
#   facescan.set <hexkey> <amount>     set one face modifier (0 removes it)
#   facescan.apply <file>              apply facescan/in/<file> (sculpts + face_modifiers)
#
# Must stay Python 3.7 compatible (the game's interpreter since 2018).
import binascii
import json
import os
import struct
import sys
import time
import traceback

MOD_VERSION = "0.3.0"
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

# Guided test (facescan.step): checkpoint label -> what the player does next.
CHECKPOINTS = ("live_applied", "after_cas", "after_save", "after_reload", "after_cas_reopen")
NEXT_STEP = {
    "begin": "NEXT: look at the Sim's face. Did it change (wider nose and mouth, bigger eyes, chin forward)? "
             "Note yes/no. Then type: facescan.step",
    "live_applied": "NEXT: type 'testingcheats true', shift-click the Sim, choose 'Modify in CAS'. Change NOTHING. "
                    "Look at the face, then click the checkmark to leave CAS. Then type: facescan.step",
    "after_cas": "NEXT: save the game (Esc > Save). Then type: facescan.step",
    "after_save": "NEXT: Esc > Main Menu, load this same save, select the FaceScanTest Sim. Then type: facescan.step",
    "after_reload": "NEXT: open 'Modify in CAS' again, change nothing, leave with the checkmark, SAVE the game. "
                    "Then type: facescan.step",
    "after_cas_reopen": "TEST COMPLETE. Quit the game, then double-click E2_check_results.bat. "
                        "(Optional, any time: facescan.undo restores the original face.)",
}

_backups = {}


def fnv64(name):
    h = 0xCBF29CE484222325
    for b in name.lower().encode("ascii"):
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        h ^= b
    return h


def _root():
    # .../The Sims 4/Mods/<file>.ts4script/facescan_bridge.pyc      (packaged)
    # .../The Sims 4/Mods/FaceScanBridge/Scripts/facescan_bridge.py (loose scripts)
    # -> .../The Sims 4/facescan
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


def _log(message):
    """Append to facescan_log.txt; never raises."""
    try:
        with open(os.path.join(_root(), "facescan_log.txt"), "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _install_method():
    f = __file__.lower().replace("\\", "/")
    return "ts4script" if ".ts4script/" in f else "scripts-folder"


def _write_heartbeat(**extra):
    try:
        data = {"mod_version": MOD_VERSION, "python": sys.version, "file": __file__,
                "install_method": _install_method(), "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "loaded_epoch": time.time()}
        data.update(extra)
        with open(os.path.join(_root(), "mod_loaded.json"), "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# --- Game modules.  Import failures are recorded instead of silently killing the mod.
_IMPORT_ERROR = None
try:
    import services
    import sims4.commands
    from protocolbuffers import PersistenceBlobs_pb2
except Exception:
    _IMPORT_ERROR = traceback.format_exc()

_write_heartbeat(import_error=_IMPORT_ERROR, commands_registered=False)
_log("mod %s loaded from %s (python %s)%s" % (MOD_VERSION, __file__, sys.version.split()[0],
                                              "; IMPORT ERROR:\n" + _IMPORT_ERROR if _IMPORT_ERROR else ""))


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


def _load_record(sim_info):
    path = _record_path(sim_info)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_record(sim_info, record):
    with open(_record_path(sim_info), "w") as f:
        json.dump(record, f, indent=2)


def _begin(sim_info):
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
        "python": sys.version.split()[0], "install_method": _install_method(),
        "sim_id": sim_info.sim_id, "sim": _sim_label(sim_info), "started": time.time(),
        "baseline_hex": _hex(baseline), "expected_hex": _hex(expected),
        "readback_identical": written == expected,
        "test_face": [{"name": n, "key": "0x%016X" % fnv64(n), "amount": a, "role": r} for n, a, r in TEST_FACE],
        "removed": [{"name": n, "key": "0x%016X" % fnv64(n)} for n in OPPOSITES],
        "checkpoints": [],
    }
    _save_record(sim_info, record)
    same = "identical" if written == expected else "DIFFERENT (%d vs %d bytes)" % (len(written), len(expected))
    return "facescan: test face applied; read-back is %s" % same


def _check(sim_info, record, label):
    probes = set(fnv64(t["name"]) for t in record["test_face"] if t["role"] == "probe")
    actual = sim_info.facial_attributes
    core, probe = _compare(binascii.unhexlify(record["expected_hex"]), actual, probes)
    result = "PASS" if not core else "FAIL"
    record["checkpoints"].append({"label": label, "time": time.time(), "result": result,
                                  "blob_hex": _hex(actual), "core_problems": core,
                                  "probe_observations": probe})
    _save_record(sim_info, record)
    lines = ["facescan: checkpoint %s: %s (%d problems, %d probe changes)" % (label, result, len(core), len(probe))]
    lines += ["  " + p for p in (core + probe)[:8]]
    return "\n".join(lines)


def _probe_api(sim_info):
    keys = ("facial", "sculpt", "modif", "physique", "genetic", "resend", "appearance", "outfit", "cas", "age")
    names = sorted(n for n in dir(sim_info) if any(k in n.lower() for k in keys))
    raw = sim_info.facial_attributes
    data = {"sim_info_type": "%s.%s" % (type(sim_info).__module__, type(sim_info).__name__),
            "facial_attributes_type": type(raw).__name__, "facial_attributes_len": len(raw) if raw is not None else None,
            "matching_attributes": names, "python": sys.version, "mod_version": MOD_VERSION}
    with open(os.path.join(_root(), "out", "api_probe.json"), "w") as f:
        json.dump(data, f, indent=2)
    return data


def _run(_connection, name, fn, needs_write):
    out = sims4.commands.CheatOutput(_connection)
    try:
        sim_info = _active_sim_info()
        if sim_info is None:
            out("facescan: no active Sim")
            _log("%s: no active Sim" % name)
            return
        if needs_write:
            refusal = _write_allowed(sim_info)
            if refusal:
                out("facescan: " + refusal)
                _log("%s on %s: %s" % (name, _sim_label(sim_info), refusal))
                return
        text = fn(sim_info)
        _log("%s on %s:\n    %s" % (name, _sim_label(sim_info), text.replace("\n", "\n    ")))
        for line in text.split("\n"):
            out(line)
    except Exception as e:  # report to the console and the log; never let an error escape into the game loop
        _log("%s FAILED:\n%s" % (name, traceback.format_exc()))
        out("facescan error in %s: %r (details in facescan_log.txt)" % (name, e))


def _register():
    live = sims4.commands.CommandType.Live

    @sims4.commands.Command("facescan.info", command_type=live)
    def facescan_info(_connection=None):
        def run(sim_info):
            refusal = _write_allowed(sim_info)
            probe = _probe_api(sim_info)
            return "\n".join([
                "facescan %s, python %s, installed as %s" % (MOD_VERSION, sys.version.split()[0], _install_method()),
                "data folder %s" % _root(),
                "active Sim: %s, species %s" % (_sim_label(sim_info), getattr(sim_info, "species", "?")),
                "facial_attributes: %s, %s bytes" % (probe["facial_attributes_type"], probe["facial_attributes_len"]),
                "writes: " + ("allowed" if refusal is None else refusal),
            ])
        _run(_connection, "info", run, needs_write=False)

    @sims4.commands.Command("facescan.dump", command_type=live)
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
        _run(_connection, "dump", run, needs_write=False)

    @sims4.commands.Command("facescan.step", command_type=live)
    def facescan_step(_connection=None):
        def run(sim_info):
            record = _load_record(sim_info)
            if record is None:
                refusal = _write_allowed(sim_info)
                if refusal:
                    return "facescan: " + refusal + "\nSelect the FaceScanTest Sim, then type: facescan.step"
                try:
                    _probe_api(sim_info)  # diagnostics only; must never block the test
                except Exception:
                    _log("api probe FAILED (test continues):\n" + traceback.format_exc())
                return _begin(sim_info) + " (step 1 of 6)\n" + NEXT_STEP["begin"]
            done = len(record["checkpoints"])
            if done >= len(CHECKPOINTS):
                return "facescan: test already complete for this Sim.\n" + NEXT_STEP["after_cas_reopen"]
            label = CHECKPOINTS[done]
            text = _check(sim_info, record, label)
            return text + " (step %d of 6)\n" % (done + 2) + NEXT_STEP[label]
        _run(_connection, "step", run, needs_write=False)

    @sims4.commands.Command("facescan.undo", command_type=live)
    def facescan_undo(_connection=None):
        def run(sim_info):
            record = _load_record(sim_info)
            if record is None:
                return "facescan: no test in progress for this Sim; nothing to undo"
            sim_info.facial_attributes = binascii.unhexlify(record["baseline_hex"])
            record["undone"] = time.time()
            done_path = _record_path(sim_info).replace(".json", ".done-%d.json" % int(time.time()))
            with open(done_path, "w") as f:
                json.dump(record, f, indent=2)
            os.remove(_record_path(sim_info))
            return "facescan: original face restored; test closed (record kept as %s)" % os.path.basename(done_path)
        _run(_connection, "undo", run, needs_write=True)

    @sims4.commands.Command("facescan.validate_begin", command_type=live)
    def facescan_validate_begin(_connection=None):
        _run(_connection, "validate_begin", _begin, needs_write=True)

    @sims4.commands.Command("facescan.validate_check", command_type=live)
    def facescan_validate_check(label="check", _connection=None):
        def run(sim_info):
            record = _load_record(sim_info)
            if record is None:
                return "facescan: no validation record for this Sim; run facescan.step first"
            return _check(sim_info, record, label)
        _run(_connection, "validate_check", run, needs_write=False)

    @sims4.commands.Command("facescan.validate_restore", command_type=live)
    def facescan_validate_restore(_connection=None):
        def run(sim_info):
            record = _load_record(sim_info)
            if record is None:
                return "facescan: no validation record for this Sim"
            sim_info.facial_attributes = binascii.unhexlify(record["baseline_hex"])
            return "facescan: baseline face restored"
        _run(_connection, "validate_restore", run, needs_write=True)

    @sims4.commands.Command("facescan.set", command_type=live)
    def facescan_set(key=None, amount="0", _connection=None):
        def run(sim_info):
            if key is None:
                return "usage: facescan.set <hexkey> <amount>"
            blob = _parse(sim_info.facial_attributes)
            _set_face_modifier(blob, int(key, 16), float(amount))
            _write_blob(sim_info, blob.SerializeToString())
            return "facescan: set %s = %s" % (key, amount)
        _run(_connection, "set", run, needs_write=True)

    @sims4.commands.Command("facescan.apply", command_type=live)
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
        _run(_connection, "apply", run, needs_write=True)


if _IMPORT_ERROR is None:
    try:
        _register()
        _write_heartbeat(import_error=None, commands_registered=True)
        _log("commands registered")
    except Exception:
        _err = traceback.format_exc()
        _write_heartbeat(import_error=None, commands_registered=False, register_error=_err)
        _log("command registration FAILED:\n" + _err)
