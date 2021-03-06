from typing import Dict

from sequence.components.memory import Memory, MemoryArray
from sequence.kernel.event import Event
from sequence.kernel.process import Process
from sequence.kernel.timeline import Timeline
from sequence.entanglement_management.entanglement_protocol import EntanglementProtocol
from sequence.topology.node import QuantumRouter


class DumbReceiver():
    def __init__(self):
        self.photon_list = []

    def send_qubit(self, dst, photon):
        self.photon_list.append(photon)


class DumbParent():
    def __init__(self, memory):
        memory.attach(self)
        self.pop_log = []

    def memory_expire(self, memory):
        self.pop_log.append(memory)


def test_MemoryArray_init():
    tl = Timeline()
    ma = MemoryArray("ma", tl, num_memories=10)

    assert len(ma.memories) == 10
    for m in ma.memories:
        assert type(m) == Memory


def test_MemoryArray_expire():
    class FakeNode(QuantumRouter):
        def __init__(self, tl):
            super().__init__("fake", tl)
            self.ma = MemoryArray("ma", tl)
            self.ma.set_node(self)
            self.is_expired = False
            self.expired_memory = -1

        def memory_expire(self, memory: "Memory") -> None:
            self.is_expired = True
            self.expired_memory = memory

    tl = Timeline()
    node = FakeNode(tl)
    ma = node.ma
    expired_memo = ma[0]
    ma.memory_expire(expired_memo)
    assert node.is_expired is True and node.expired_memory == expired_memo


def test_Memory_excite():
    NUM_TESTS = 1000

    tl = Timeline()
    rec = DumbReceiver()
    mem = Memory("mem", tl, fidelity=1, frequency=0, efficiency=1, coherence_time=-1, wavelength=500)
    mem.owner = rec

    # test with perfect efficiency

    state = (complex(1), complex(0))
    mem.qstate.set_state_single(state)

    for _ in range(NUM_TESTS):
        mem.excite()

    assert len(rec.photon_list) == NUM_TESTS
    null_photons = [p for p in rec.photon_list if p.is_null]
    null_ratio = len(null_photons) / NUM_TESTS
    assert null_ratio == 1

    # test with imperfect efficiency

    rec.photon_list = []
    mem.efficiency = 0.7
    state = (complex(0), complex(1))
    mem.qstate.set_state_single(state)

    for _ in range(NUM_TESTS):
        mem.excite()

    assert abs(len(rec.photon_list) / NUM_TESTS - 0.7) < 0.1
    null_photons = [p for p in rec.photon_list if p.is_null]
    null_ratio = len(null_photons) / len(rec.photon_list)
    assert null_ratio == 0

    # test with perfect efficiency, + state

    rec.photon_list = []
    mem.efficiency = 1

    for _ in range(NUM_TESTS):
       mem.set_plus()
       mem.excite()

    assert len(rec.photon_list) == NUM_TESTS
    null_photons = [p for p in rec.photon_list if p.is_null]
    null_ratio = len(null_photons) / NUM_TESTS
    assert abs(null_ratio - 0.5) < 0.1


def test_Memory_flip_state():
    tl = Timeline()
    rec = DumbReceiver()
    mem = Memory("mem", tl, fidelity=1, frequency=0, efficiency=1, coherence_time=-1, wavelength=500)
    mem.owner = rec
    state = (complex(1), complex(0))
    mem.qstate.set_state_single(state)

    mem.excite()
    mem.flip_state()
    mem.excite()

    assert rec.photon_list[0].is_null
    assert not rec.photon_list[1].is_null


def test_Memory_expire():
    class FakeProtocol(EntanglementProtocol):
        def __init__(self, name):
            super().__init__(None, name)
            self.is_expire = False

        def set_others(self, other: "EntanglementProtocol") -> None:
            pass

        def start(self) -> None:
            pass

        def is_ready(self) -> bool:
            pass

        def memory_expire(self, memory) -> None:
            self.is_expire = True

        def received_message(self, src: str, msg: "Message"):
            pass

        def expire(self, memory: Memory):
            self.memory_expire(memory)

    tl = Timeline()
    mem = Memory("mem", tl, fidelity=1, frequency=0, efficiency=1, coherence_time=-1, wavelength=500)
    parent = DumbParent(mem)
    protocol = FakeProtocol("upper_protocol")
    mem.attach(protocol)
    mem.set_plus()
    entangled_memory = {"node_id": "node", "memo_id": 0}
    mem.entangled_memory = entangled_memory

    # expire when the protocol controls memory
    mem.detach(parent)
    assert len(parent.pop_log) == 0 and protocol.is_expire is False
    mem.expire()
    assert (complex(1), complex(0)) == mem.qstate.state  # check if collapsed to |0> state
    assert mem.entangled_memory == {"node_id": None, "memo_id": None}
    assert len(parent.pop_log) == 0 and protocol.is_expire is True

    # expire when the resource manager controls memory
    mem.attach(parent)
    mem.detach(protocol)
    mem.set_plus()
    entangled_memory = {"node_id": "node", "memo_id": 0}
    mem.entangled_memory = entangled_memory
    mem.expire()
    assert len(parent.pop_log) == 1


def test_Memory__schedule_expiration():
    tl = Timeline()
    mem = Memory("mem", tl, fidelity=1, frequency=0, efficiency=1, coherence_time=1, wavelength=500)
    parent = DumbParent(mem)

    process = Process(mem, "expire", [])
    event = Event(1e12, process)
    tl.schedule(event)
    mem.expiration_event = event

    mem._schedule_expiration()

    counter = 0
    for event in tl.events:
        if event.is_invalid():
            counter += 1
    assert counter == 1
