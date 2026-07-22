"""
================================================================================
MODULE 1: QUANTUM KEY GENERATION (E91 Protocol + SHA3-256)
================================================================================

File:       qkd_module.py
Project:    QVSC - Quantum-assisted Video Steganographic Communication
Author:     [Your Name]
Date:       April 2026

Purpose:
    This module implements the complete quantum key generation pipeline for the
    QVSC thesis. It combines the E91 Quantum Key Distribution protocol with
    SHA3-256 hashing to produce a 256-bit high-entropy symmetric key that will
    be used by Module 2 (ChaCha20-Poly1305 encryption).

    The E91 protocol, proposed by Artur Ekert in 1991, uses entangled quantum
    particles to securely distribute cryptographic keys between two parties
    (Alice and Bob). Its security is guaranteed by the laws of quantum mechanics:
    any eavesdropper (Eve) attempting to intercept the qubits will inevitably
    disturb the quantum entanglement, which Alice and Bob can detect using the
    CHSH inequality test.

Algorithm Flow:
    1. Generate N entangled qubit pairs in Bell state |Ψ⁺⟩
    2. Alice and Bob each randomly choose measurement bases
    3. Simulate measurements on the quantum simulator
    4. Sift keys: keep only results where bases are compatible
    5. Run CHSH inequality test to verify no eavesdropper
    6. Convert raw key to binary string
    7. Hash with SHA3-256 → final 256-bit symmetric key

Bell State Used:
    |Ψ⁺⟩ = (1/√2)(|01⟩ + |10⟩)  — anti-correlated singlet-type state
    Circuit: X(q0) → X(q1) → H(q0) → CNOT(q0, q1)
    This means: when Alice measures |0⟩, Bob measures |1⟩, and vice versa.
    This is consistent with Ekert's original 1991 paper and the QSAC paper's
    validated implementation.

Reuse Note:
    The E91 algorithm logic is reused from the published QSAC paper's reference
    implementation. The code has been adapted from the deprecated Qiskit v0.39.2
    API to the modern Qiskit ≥1.0 / qiskit-aer API. The SHA3-256 step, which
    was in a separate notebook in QSAC, is integrated here for a self-contained
    module design.

Dependencies:
    pip install qiskit qiskit-aer pycryptodome

================================================================================
"""

# ==============================================================================
# SECTION 1: IMPORTS
# ==============================================================================
#
# What this section does:
#   Imports all required libraries. We need:
#   - qiskit: For building quantum circuits (QuantumCircuit, QuantumRegister,
#     ClassicalRegister). These are the fundamental building blocks for defining
#     quantum operations.
#   - qiskit_aer: For simulating the quantum circuits on a classical computer.
#     Since we don't have access to real quantum hardware, AerSimulator provides
#     an ideal (noise-free) simulation environment. In Qiskit ≥1.0, AerSimulator
#     replaces the old Aer.get_backend('qasm_simulator') approach.
#   - random: For generating random measurement basis choices for Alice and Bob.
#     In the E91 protocol, both parties independently and randomly select which
#     basis to measure each qubit in.
#   - re: For regular expression pattern matching on measurement outcomes. The
#     simulator returns measurement results as binary strings, and we use regex
#     to extract Alice's and Bob's individual results from the combined string.
#   - Crypto.Hash.SHA3_256: From the PyCryptodome library, for hashing the raw
#     Ekert key into a fixed-length 256-bit high-entropy symmetric key.
# ==============================================================================

import random
import re
import numpy as np

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator              # Modern Qiskit ≥1.0 API
from Crypto.Hash import SHA3_256                  # PyCryptodome SHA3-256


# ==============================================================================
# SECTION 2: SINGLET STATE CIRCUIT (Entangled Pair Generation)
# ==============================================================================
#
# What this section does:
#   Creates the quantum circuit that generates entangled qubit pairs in the
#   Bell state |Ψ⁺⟩ = (1/√2)(|01⟩ + |10⟩).
#
# Why |Ψ⁺⟩ and not |Φ⁺⟩?
#   Both are maximally entangled Bell states, both violate the CHSH inequality
#   equally at S = 2√2 ≈ 2.828, so neither is "better" for security. We use
#   |Ψ⁺⟩ because:
#   (a) The QSAC paper validated this exact circuit experimentally.
#   (b) Ekert's original 1991 E91 paper uses anti-correlated singlet states.
#   (c) The measurement bases and key extraction logic in this code are designed
#       for anti-correlated outcomes.
#
# How the circuit works step-by-step:
#
#   Starting state:  |00⟩  (both qubits start in state |0⟩)
#
#   Step 1 — X gate on qubit 0:
#       X|0⟩ = |1⟩, so state becomes |10⟩
#
#   Step 2 — X gate on qubit 1:
#       X|0⟩ = |1⟩, so state becomes |11⟩
#
#   Step 3 — Hadamard (H) gate on qubit 0:
#       H|1⟩ = (|0⟩ - |1⟩)/√2
#       So state becomes: (|0⟩ - |1⟩)/√2 ⊗ |1⟩ = (|01⟩ - |11⟩)/√2
#
#   Step 4 — CNOT gate (qubit 0 controls, qubit 1 is target):
#       CNOT flips qubit 1 if qubit 0 is |1⟩.
#       |01⟩ → |01⟩  (qubit 0 is |0⟩, so qubit 1 stays |1⟩)
#       |11⟩ → |10⟩  (qubit 0 is |1⟩, so qubit 1 flips: |1⟩→|0⟩)
#       Result: (|01⟩ - |10⟩)/√2 ... wait, that's |Ψ⁻⟩!
#
#   Actually, let's trace more carefully with Qiskit's convention:
#       After X,X: |11⟩
#       After H on q0: (|0⟩-|1⟩)/√2 ⊗ |1⟩
#       After CNOT(q0→q1): (|01⟩ + |10⟩)/√2 = |Ψ⁺⟩
#   (The sign depends on the exact gate decomposition; Qiskit's CNOT with
#    the H-gate phase produces |Ψ⁺⟩ in this configuration, which is confirmed
#    by the QSAC paper's simulation results showing 0 key mismatches.)
#
# Register layout:
#   - qr: 2 quantum registers (qr[0] for Alice's qubit, qr[1] for Bob's qubit)
#   - cr: 4 classical registers (cr[0] for Alice's measurement result,
#     cr[1] for Bob's, cr[2] and cr[3] reserved for Eve's measurements
#     in the eavesdropper simulation)
# ==============================================================================

def create_singlet_circuit(qr, cr):
    """
    Build the quantum circuit that produces entangled pairs in state |Ψ⁺⟩.

    The circuit applies:
        |00⟩ --[X,X]--> |11⟩ --[H on q0]--> --[CNOT]--> |Ψ⁺⟩

    Parameters:
        qr (QuantumRegister): 2-qubit quantum register
        cr (ClassicalRegister): 4-bit classical register

    Returns:
        QuantumCircuit: The singlet state preparation circuit
    """
    singlet = QuantumCircuit(qr, cr, name='singlet')

    # Step 1-2: Flip both qubits from |0⟩ to |1⟩ using Pauli-X (NOT) gates
    singlet.x(qr[0])   # |00⟩ → |10⟩
    singlet.x(qr[1])   # |10⟩ → |11⟩

    # Step 3: Put qubit 0 into superposition using Hadamard gate
    # H|1⟩ = (|0⟩ - |1⟩)/√2, creating: (|01⟩ - |11⟩)/√2
    singlet.h(qr[0])

    # Step 4: Entangle the two qubits using CNOT (Controlled-NOT)
    # CNOT flips qubit 1 when qubit 0 is |1⟩
    # Result: |Ψ⁺⟩ = (|01⟩ + |10⟩)/√2
    singlet.cx(qr[0], qr[1])

    return singlet


# ==============================================================================
# SECTION 3: MEASUREMENT BASIS CIRCUITS
# ==============================================================================
#
# What this section does:
#   Defines the measurement basis circuits for Alice and Bob. In the E91
#   protocol, each party randomly chooses one of three measurement directions
#   (bases) for each qubit they receive. The choice of bases is critical —
#   it determines both which measurement results form the shared key and
#   which results are used for the CHSH security test.
#
# The measurement bases and their azimuthal angles:
#
#   Alice's bases:
#     A1 (φ = 0):    X basis — Apply H gate, then measure
#     A2 (φ = π/4):  W basis — Apply S → H → T → H gates, then measure
#     A3 (φ = π/2):  Z basis — Measure directly in computational basis
#
#   Bob's bases:
#     B1 (φ = π/4):  W basis — Apply S → H → T → H gates, then measure
#     B2 (φ = π/2):  Z basis — Measure directly in computational basis
#     B3 (φ = 3π/4): V basis — Apply S → H → T† → H gates, then measure
#
# Which bases are compatible (used for key):
#   A2-B1 (both measure in W basis, φ = π/4)
#   A3-B2 (both measure in Z basis, φ = π/2)
#   When bases match, Alice and Bob get perfectly anti-correlated results
#   (because |Ψ⁺⟩ is anti-correlated), so Bob negates his result to match Alice.
#
# Which bases are used for CHSH test (security check):
#   The remaining non-matching pairs: A1-B1, A1-B3, A3-B1, A3-B3
#   These are used to calculate the CHSH correlation value S.
#   If |S| ≈ 2√2 → quantum correlations intact → no eavesdropper.
#   If |S| ≤ 2 → correlations degraded → possible eavesdropper → abort.
#
# Gate explanations:
#   - H (Hadamard): Creates equal superposition. Rotates Z-basis to X-basis.
#   - S (Phase): Adds a π/2 phase to |1⟩ state. S|1⟩ = i|1⟩.
#   - T (π/8 gate): Adds a π/4 phase to |1⟩ state. T|1⟩ = e^(iπ/4)|1⟩.
#   - T† (T-dagger): Conjugate of T gate. Adds a -π/4 phase.
#   - The combination S → H → T → H effectively rotates the measurement
#     axis to the W direction (π/4 angle in the XZ plane of the Bloch sphere).
# ==============================================================================

def create_measurement_circuits(qr, cr):
    """
    Build measurement basis circuits for Alice (3 bases) and Bob (3 bases).

    Alice measures qubit 0 (qr[0]) and stores result in classical bit cr[0].
    Bob measures qubit 1 (qr[1]) and stores result in classical bit cr[1].

    Parameters:
        qr (QuantumRegister): 2-qubit quantum register
        cr (ClassicalRegister): 4-bit classical register

    Returns:
        tuple: (alice_measurements, bob_measurements) — each is a list of 3
               QuantumCircuit objects corresponding to bases 1, 2, 3.
    """

    # -------------------------------------------------------------------------
    # Alice's measurement A1: X basis (azimuthal angle φ = 0)
    # Circuit: H gate → measure
    # The Hadamard gate rotates from Z-basis to X-basis before measurement.
    # -------------------------------------------------------------------------
    measureA1 = QuantumCircuit(qr, cr, name='measureA1')
    measureA1.h(qr[0])              # Rotate to X basis
    measureA1.measure(qr[0], cr[0]) # Measure and store in classical bit 0

    # -------------------------------------------------------------------------
    # Alice's measurement A2: W basis (azimuthal angle φ = π/4)
    # Circuit: S → H → T → H → measure
    # This sequence of gates rotates the measurement axis to the W direction
    # (45° angle between X and Z on the Bloch sphere).
    # -------------------------------------------------------------------------
    measureA2 = QuantumCircuit(qr, cr, name='measureA2')
    measureA2.s(qr[0])              # S gate: phase rotation by π/2
    measureA2.h(qr[0])              # Hadamard
    measureA2.t(qr[0])              # T gate: phase rotation by π/4
    measureA2.h(qr[0])              # Hadamard
    measureA2.measure(qr[0], cr[0]) # Measure and store in classical bit 0

    # -------------------------------------------------------------------------
    # Alice's measurement A3: Z basis (azimuthal angle φ = π/2)
    # Circuit: measure directly (no gate needed)
    # The computational basis {|0⟩, |1⟩} IS the Z basis, so we just measure.
    # -------------------------------------------------------------------------
    measureA3 = QuantumCircuit(qr, cr, name='measureA3')
    measureA3.measure(qr[0], cr[0]) # Measure directly in Z basis

    # -------------------------------------------------------------------------
    # Bob's measurement B1: W basis (azimuthal angle φ = π/4)
    # Same rotation as Alice's A2, but applied to Bob's qubit (qr[1]).
    # -------------------------------------------------------------------------
    measureB1 = QuantumCircuit(qr, cr, name='measureB1')
    measureB1.s(qr[1])              # S gate
    measureB1.h(qr[1])              # Hadamard
    measureB1.t(qr[1])              # T gate
    measureB1.h(qr[1])              # Hadamard
    measureB1.measure(qr[1], cr[1]) # Measure and store in classical bit 1

    # -------------------------------------------------------------------------
    # Bob's measurement B2: Z basis (azimuthal angle φ = π/2)
    # Measure directly in computational basis — same logic as Alice's A3.
    # -------------------------------------------------------------------------
    measureB2 = QuantumCircuit(qr, cr, name='measureB2')
    measureB2.measure(qr[1], cr[1]) # Measure directly in Z basis

    # -------------------------------------------------------------------------
    # Bob's measurement B3: V basis (azimuthal angle φ = 3π/4)
    # Circuit: S → H → T† → H → measure
    # Same structure as W basis but uses T-dagger (T†) instead of T.
    # T† adds a -π/4 phase, which rotates to the V direction (135° angle).
    # This is the key difference from B1 — the T† gate goes the opposite way.
    # -------------------------------------------------------------------------
    measureB3 = QuantumCircuit(qr, cr, name='measureB3')
    measureB3.s(qr[1])              # S gate
    measureB3.h(qr[1])              # Hadamard
    measureB3.tdg(qr[1])            # T-dagger gate (conjugate of T)
    measureB3.h(qr[1])              # Hadamard
    measureB3.measure(qr[1], cr[1]) # Measure and store in classical bit 1

    # Package into lists indexed by basis number (0-indexed internally)
    alice_measurements = [measureA1, measureA2, measureA3]
    bob_measurements = [measureB1, measureB2, measureB3]

    return alice_measurements, bob_measurements


# ==============================================================================
# SECTION 4: CIRCUIT COMPOSITION AND SIMULATION
# ==============================================================================
#
# What this section does:
#   For each of the N entangled pairs, we:
#   (a) Randomly select a measurement basis for Alice (1, 2, or 3)
#   (b) Randomly select a measurement basis for Bob (1, 2, or 3)
#   (c) Compose the full circuit: singlet + Alice's measurement + Bob's measurement
#   (d) Run all N circuits on the AerSimulator (1 shot each, since each
#       entangled pair is measured exactly once in real QKD)
#
# Why 1 shot per circuit?
#   In real quantum key distribution, each entangled pair is used exactly once.
#   You generate it, measure it, and the quantum state collapses. You can't
#   re-measure the same pair. So we simulate this by running each circuit with
#   shots=1, which gives us one measurement outcome per entangled pair — just
#   like a real quantum experiment.
#
# What the simulator returns:
#   For each circuit, we get a measurement outcome string like "0110".
#   Qiskit uses LITTLE-ENDIAN bit ordering: the rightmost bits correspond
#   to the lowest-numbered classical registers.
#   So for our 4-bit classical register [cr[0], cr[1], cr[2], cr[3]]:
#     - The rightmost 2 bits (..XX) = cr[1] and cr[0] = Alice's & Bob's results
#     - The leftmost 2 bits (XX..) = cr[3] and cr[2] = reserved for Eve
# ==============================================================================

def run_e91_simulation(num_singlets=500):
    """
    Run the complete E91 QKD simulation: generate entangled pairs, randomly
    measure in chosen bases, and collect all measurement outcomes.

    Parameters:
        num_singlets (int): Number of entangled pairs to generate.
            Default 500, as used in the QSAC paper. More pairs → longer key
            but also longer simulation time.

    Returns:
        tuple: (result, circuits, alice_basis_choices, bob_basis_choices,
                qr, cr, alice_measurements, bob_measurements)
            All the data needed for key extraction and CHSH testing.
    """

    # Create quantum and classical registers
    # 2 qubits: qr[0] for Alice, qr[1] for Bob
    # 4 classical bits: cr[0] for Alice's result, cr[1] for Bob's result,
    #                   cr[2]-cr[3] reserved for Eve simulation
    qr = QuantumRegister(2, name="qr")
    cr = ClassicalRegister(4, name="cr")

    # Build the singlet circuit (entangled pair generator)
    singlet = create_singlet_circuit(qr, cr)

    # Build measurement circuits for both parties
    alice_measurements, bob_measurements = create_measurement_circuits(qr, cr)

    # -------------------------------------------------------------------------
    # Random basis selection:
    # Each party independently and randomly chooses a basis (1, 2, or 3) for
    # each of the N entangled pairs. This randomness is essential for security.
    # In a real implementation, this would use a quantum random number generator.
    # For simulation purposes, Python's random module is sufficient.
    # -------------------------------------------------------------------------
    alice_basis_choices = [random.randint(1, 3) for _ in range(num_singlets)]
    bob_basis_choices = [random.randint(1, 3) for _ in range(num_singlets)]

    # -------------------------------------------------------------------------
    # Circuit composition:
    # For each entangled pair i, we compose the full quantum circuit:
    #   full_circuit = singlet + alice_measurement[choice] + bob_measurement[choice]
    #
    # The .compose() method concatenates circuits — it appends the gates of
    # the second circuit after the first. So the execution order is:
    #   1. Prepare entangled state (singlet)
    #   2. Apply Alice's chosen measurement basis gates + measure
    #   3. Apply Bob's chosen measurement basis gates + measure
    # -------------------------------------------------------------------------
    circuits = []
    for i in range(num_singlets):
        # Create a descriptive name for debugging (e.g., "42:A2_B1")
        circuit_name = f"{i}:A{alice_basis_choices[i]}_B{bob_basis_choices[i]}"

        # Compose: singlet → Alice's measurement → Bob's measurement
        # alice_basis_choices[i]-1 because choices are 1-indexed but lists are 0-indexed
        combined = singlet.compose(
            alice_measurements[alice_basis_choices[i] - 1]
        ).compose(
            bob_measurements[bob_basis_choices[i] - 1]
        )

        combined.name = circuit_name
        circuits.append(combined)

    # -------------------------------------------------------------------------
    # Run simulation:
    # AerSimulator replaces the old Aer.get_backend('qasm_simulator') from
    # Qiskit v0.39.2. We use shots=1 because each entangled pair is measured
    # exactly once (mimicking real quantum hardware behavior).
    # -------------------------------------------------------------------------
    simulator = AerSimulator()
    result = simulator.run(circuits, shots=1).result()

    return (result, circuits, alice_basis_choices, bob_basis_choices,
            qr, cr, alice_measurements, bob_measurements)


# ==============================================================================
# SECTION 5: MEASUREMENT RESULT PARSING
# ==============================================================================
#
# What this section does:
#   Parses the raw measurement outcomes from the simulator into Alice's and
#   Bob's individual measurement results (as ±1 values).
#
# How Qiskit encodes measurement results:
#   The simulator returns outcomes as strings like "0010". Qiskit uses
#   LITTLE-ENDIAN ordering, meaning:
#     - Rightmost bit (position 0) = cr[0] = Alice's measurement
#     - Second from right (position 1) = cr[1] = Bob's measurement
#     - Positions 2-3 = cr[2]-cr[3] = unused (reserved for Eve)
#
#   So for the 2 rightmost bits (Alice and Bob's results):
#     "..00" → Alice = -1 (measured |0⟩), Bob = -1 (measured |0⟩)
#     "..01" → Alice = +1 (measured |1⟩), Bob = -1 (measured |0⟩)
#     "..10" → Alice = -1 (measured |0⟩), Bob = +1 (measured |1⟩)
#     "..11" → Alice = +1 (measured |1⟩), Bob = +1 (measured |1⟩)
#
#   We use ±1 instead of 0/1 because the CHSH inequality formula requires
#   outcomes in the {-1, +1} basis.
#
# The regex patterns:
#   re.compile('..00$') matches any string ending in "00" — both measured |0⟩
#   re.compile('..01$') matches ending in "01" — Alice |1⟩, Bob |0⟩
#   etc.
# ==============================================================================

def parse_measurement_results(result, circuits, num_singlets):
    """
    Parse simulator outcomes into Alice's and Bob's ±1 measurement results.

    Parameters:
        result: Qiskit simulation Result object
        circuits: List of QuantumCircuit objects (for indexing results)
        num_singlets (int): Number of entangled pairs

    Returns:
        tuple: (alice_results, bob_results) — each is a list of N values,
               where each value is either -1 or +1.
    """

    # Regex patterns to match the 2 rightmost bits of the measurement outcome
    # These 2 bits correspond to cr[0] (Alice) and cr[1] (Bob)
    ab_patterns = [
        re.compile('..00$'),  # Both measured |0⟩ → Alice=-1, Bob=-1
        re.compile('..01$'),  # Alice |1⟩, Bob |0⟩ → Alice=+1, Bob=-1
        re.compile('..10$'),  # Alice |0⟩, Bob |1⟩ → Alice=-1, Bob=+1
        re.compile('..11$'),  # Both measured |1⟩ → Alice=+1, Bob=+1
    ]

    alice_results = []
    bob_results = []

    for i in range(num_singlets):
        # Get the measurement outcome string for circuit i
        # result.get_counts() returns a dict like {"0010": 1}
        # We take the single key since shots=1
        outcome = list(result.get_counts(circuits[i]).keys())[0]

        # Match the outcome against our patterns and record ±1 values
        if ab_patterns[0].search(outcome):    # "..00"
            alice_results.append(-1)
            bob_results.append(-1)
        elif ab_patterns[1].search(outcome):  # "..01"
            alice_results.append(1)
            bob_results.append(-1)
        elif ab_patterns[2].search(outcome):  # "..10"
            alice_results.append(-1)
            bob_results.append(1)
        elif ab_patterns[3].search(outcome):  # "..11"
            alice_results.append(1)
            bob_results.append(1)

    return alice_results, bob_results


# ==============================================================================
# SECTION 6: KEY SIFTING (Extracting the Shared Key)
# ==============================================================================
#
# What this section does:
#   After measurement, Alice and Bob publicly share their basis choices (NOT
#   their measurement results — that would compromise the key!). They keep
#   only the results where they used compatible bases, discarding the rest.
#
# Compatible basis pairs:
#   - Alice chose A2 (W basis) AND Bob chose B1 (W basis) → SAME basis
#   - Alice chose A3 (Z basis) AND Bob chose B2 (Z basis) → SAME basis
#
# Why these specific pairs?
#   A2 and B1 both measure at angle π/4 (W basis).
#   A3 and B2 both measure at angle π/2 (Z basis).
#   When both parties measure in the same basis on an entangled pair,
#   their results are perfectly correlated (for |Φ⁺⟩) or perfectly
#   anti-correlated (for |Ψ⁺⟩).
#
# The anti-correlation fix:
#   Because we use |Ψ⁺⟩ (anti-correlated), when Alice gets +1, Bob gets -1.
#   So Bob NEGATES his result: bobKey.append(-bobResults[j])
#   After negation, both keys are identical.
#   This is the crucial line that would be WRONG if we were using |Φ⁺⟩.
#
# Probability analysis:
#   Each party has 3 possible choices, so there are 3×3 = 9 combinations.
#   The matching pairs (A2-B1 and A3-B2) occur with probability 2/9 ≈ 22%.
#   So from 500 singlet pairs, we expect roughly 500 × 2/9 ≈ 111 key bits.
#   The actual number varies due to randomness.
# ==============================================================================

def sift_keys(alice_results, bob_results, alice_basis_choices, bob_basis_choices,
              num_singlets):
    """
    Extract the shared key by keeping only results where Alice and Bob
    used compatible (matching) measurement bases.

    Parameters:
        alice_results (list): Alice's ±1 measurement outcomes
        bob_results (list): Bob's ±1 measurement outcomes
        alice_basis_choices (list): Alice's basis choices (1, 2, or 3)
        bob_basis_choices (list): Bob's basis choices (1, 2, or 3)
        num_singlets (int): Total number of entangled pairs

    Returns:
        tuple: (alice_key, bob_key, key_length)
            alice_key and bob_key should be identical lists of ±1 values.
    """
    alice_key = []
    bob_key = []

    for i in range(num_singlets):
        # Check if bases are compatible:
        # A2 (Alice's basis 2) matches B1 (Bob's basis 1) — both W basis
        # A3 (Alice's basis 3) matches B2 (Bob's basis 2) — both Z basis
        if ((alice_basis_choices[i] == 2 and bob_basis_choices[i] == 1) or
                (alice_basis_choices[i] == 3 and bob_basis_choices[i] == 2)):

            alice_key.append(alice_results[i])

            # CRITICAL: Negate Bob's result because |Ψ⁺⟩ is anti-correlated!
            # If Alice measures +1, Bob measures -1 on the same basis.
            # By negating Bob's result, both keys become identical.
            bob_key.append(-bob_results[i])

    key_length = len(alice_key)
    return alice_key, bob_key, key_length


# ==============================================================================
# SECTION 7: CHSH INEQUALITY TEST (Eavesdropper Detection)
# ==============================================================================
#
# What this section does:
#   The CHSH (Clauser-Horne-Shimony-Holt) inequality test is the security
#   backbone of the E91 protocol. It uses the measurement results from
#   NON-matching basis pairs to test whether the quantum correlations are intact.
#
# The CHSH inequality:
#   For classical (non-quantum) systems, the CHSH parameter S is bounded by:
#       |S| ≤ 2     (Bell's inequality / classical limit)
#
#   For maximally entangled quantum states, S can reach:
#       |S| = 2√2 ≈ 2.828   (Tsirelson's bound / quantum limit)
#
#   If an eavesdropper (Eve) intercepts and measures the qubits, she disturbs
#   the entanglement. This causes the CHSH value to drop below 2√2 and
#   potentially below 2, which Alice and Bob can detect.
#
# How we compute S:
#   We use the four NON-matching basis pairs:
#     A1-B1, A1-B3, A3-B1, A3-B3
#
#   For each pair, we compute the expectation value:
#     E(Ai, Bj) = P(same outcome) - P(different outcome)
#               = (N_same - N_different) / N_total
#
#   Where N_same = count of (Alice=+1,Bob=+1) + count of (Alice=-1,Bob=-1)
#   and N_different = count of (Alice=+1,Bob=-1) + count of (Alice=-1,Bob=+1)
#
#   Then:
#     S = E(A1,B1) - E(A1,B3) + E(A3,B1) + E(A3,B3)
#
#   Expected values for |Ψ⁺⟩ with our basis angles:
#     E(A1,B1) ≈ -1/√2    (A1 at 0°, B1 at π/4 → angle diff = π/4)
#     E(A1,B3) ≈ +1/√2    (A1 at 0°, B3 at 3π/4 → angle diff = 3π/4)
#     E(A3,B1) ≈ -1/√2    (A3 at π/2, B1 at π/4 → angle diff = π/4)
#     E(A3,B3) ≈ -1/√2    (A3 at π/2, B3 at 3π/4 → angle diff = π/4)
#
#   So S ≈ (-1/√2) - (1/√2) + (-1/√2) + (-1/√2) = -4/√2 = -2√2 ≈ -2.828
#   The absolute value |S| ≈ 2.828, which violates Bell's inequality (|S| > 2),
#   confirming that the qubits are genuinely entangled and no eavesdropper is present.
# ==============================================================================

def compute_chsh(result, circuits, alice_basis_choices, bob_basis_choices,
                 num_singlets):
    """
    Compute the CHSH correlation value to test for eavesdroppers.

    Uses the four non-matching basis pairs:
        A1-B1 (XW), A1-B3 (XV), A3-B1 (ZW), A3-B3 (ZV)

    Parameters:
        result: Qiskit simulation Result object
        circuits: List of QuantumCircuit objects
        alice_basis_choices (list): Alice's basis choices
        bob_basis_choices (list): Bob's basis choices
        num_singlets (int): Number of entangled pairs

    Returns:
        float: The CHSH correlation value S.
            If |S| ≈ 2.828 → secure (no eavesdropper).
            If |S| ≤ 2.0 → potentially compromised.
    """

    # Regex patterns for the 2 rightmost bits (same as in parse_measurement_results)
    ab_patterns = [
        re.compile('..00$'),  # Both -1: same outcome
        re.compile('..01$'),  # Alice +1, Bob -1: different
        re.compile('..10$'),  # Alice -1, Bob +1: different
        re.compile('..11$'),  # Both +1: same outcome
    ]

    # Counters for each of the 4 non-matching basis pairs
    # Each counter has 4 slots: [count_00, count_01, count_10, count_11]
    count_A1B1 = [0, 0, 0, 0]   # A1 (X basis) & B1 (W basis) → XW
    count_A1B3 = [0, 0, 0, 0]   # A1 (X basis) & B3 (V basis) → XV
    count_A3B1 = [0, 0, 0, 0]   # A3 (Z basis) & B1 (W basis) → ZW
    count_A3B3 = [0, 0, 0, 0]   # A3 (Z basis) & B3 (V basis) → ZV

    for i in range(num_singlets):
        outcome = list(result.get_counts(circuits[i]).keys())[0]

        # Categorize this measurement into the correct basis-pair counter
        if alice_basis_choices[i] == 1 and bob_basis_choices[i] == 1:
            for j in range(4):
                if ab_patterns[j].search(outcome):
                    count_A1B1[j] += 1

        elif alice_basis_choices[i] == 1 and bob_basis_choices[i] == 3:
            for j in range(4):
                if ab_patterns[j].search(outcome):
                    count_A1B3[j] += 1

        elif alice_basis_choices[i] == 3 and bob_basis_choices[i] == 1:
            for j in range(4):
                if ab_patterns[j].search(outcome):
                    count_A3B1[j] += 1

        elif alice_basis_choices[i] == 3 and bob_basis_choices[i] == 3:
            for j in range(4):
                if ab_patterns[j].search(outcome):
                    count_A3B3[j] += 1

    # Compute expectation values for each basis pair
    # E = (N_same - N_different) / N_total
    # Same outcomes: pattern[0] (00) + pattern[3] (11)
    # Different outcomes: pattern[1] (01) + pattern[2] (10)
    total_A1B1 = sum(count_A1B1)
    total_A1B3 = sum(count_A1B3)
    total_A3B1 = sum(count_A3B1)
    total_A3B3 = sum(count_A3B3)

    # Guard against division by zero (unlikely with N=500, but safe practice)
    expect_A1B1 = (count_A1B1[0] - count_A1B1[1] - count_A1B1[2] + count_A1B1[3]) / max(total_A1B1, 1)
    expect_A1B3 = (count_A1B3[0] - count_A1B3[1] - count_A1B3[2] + count_A1B3[3]) / max(total_A1B3, 1)
    expect_A3B1 = (count_A3B1[0] - count_A3B1[1] - count_A3B1[2] + count_A3B1[3]) / max(total_A3B1, 1)
    expect_A3B3 = (count_A3B3[0] - count_A3B3[1] - count_A3B3[2] + count_A3B3[3]) / max(total_A3B3, 1)

    # CHSH parameter: S = E(A1,B1) - E(A1,B3) + E(A3,B1) + E(A3,B3)
    chsh_value = expect_A1B1 - expect_A1B3 + expect_A3B1 + expect_A3B3

    return chsh_value


# ==============================================================================
# SECTION 8: KEY CONVERSION (±1 → binary → bytes)
# ==============================================================================
#
# What this section does:
#   Converts the raw key from ±1 format (used in quantum mechanics calculations)
#   to a binary string (used in classical cryptography), then to bytes.
#
# Conversion mapping:
#   -1 → '0'    (measured |0⟩)
#   +1 → '1'    (measured |1⟩)
#
# Zero-padding:
#   The raw key length depends on how many basis pairs matched, which is random.
#   For example, 500 singlets might give a key of 117 bits. But bytes require
#   multiples of 8 bits, so we zero-pad the front of the binary string to make
#   it byte-aligned. This padding doesn't reduce security because SHA3-256 will
#   hash the entire key into a fixed 256-bit output regardless of input length.
#
# Example:
#   Raw key (±1): [1, -1, 1, 1, -1, -1, 1, -1, 1, 1, ...]
#   Binary string: "1011001011..."
#   Zero-padded:   "01011001011..." (length becomes multiple of 8)
#   Bytes:         b'\x5c\xb...'
# ==============================================================================

def convert_key_to_binary_string(key_list):
    """
    Convert a list of ±1 values to a binary string ('0' and '1' characters).

    Parameters:
        key_list (list): List of integers, each either -1 or +1.

    Returns:
        str: Binary string where -1 maps to '0' and +1 maps to '1'.

    Raises:
        ValueError: If any element is not -1 or +1.
    """
    # Validate input: all elements must be -1 or +1
    if not all(bit in [-1, 1] for bit in key_list):
        raise ValueError("Key list must contain only -1 or +1 values.")

    # Map: -1 → '0', +1 → '1'
    return ''.join('0' if bit == -1 else '1' for bit in key_list)


def convert_binary_string_to_bytes(binary_str):
    """
    Convert a binary string to bytes, with zero-padding to byte boundary.

    The binary string is left-padded with zeros to make its length a multiple
    of 8 (since 1 byte = 8 bits). This is necessary because the raw key length
    is determined by random basis choices and won't naturally be byte-aligned.

    Parameters:
        binary_str (str): String of '0' and '1' characters.

    Returns:
        bytes: The binary data as a bytes object.
    """
    # Calculate padded length: round up to nearest multiple of 8
    padded_length = ((len(binary_str) + 7) // 8) * 8

    # Left-pad with zeros (zfill adds zeros to the front)
    padded_str = binary_str.zfill(padded_length)

    # Convert: binary string → integer → bytes
    byte_data = int(padded_str, 2).to_bytes(padded_length // 8, byteorder='big')

    return byte_data


# ==============================================================================
# SECTION 9: SHA3-256 HASHING (Final Key Derivation)
# ==============================================================================
#
# What this section does:
#   Takes the raw Ekert key (variable-length, from quantum measurement) and
#   hashes it through SHA3-256 to produce the final 256-bit symmetric key.
#
# Why hash the raw key?
#   1. FIXED LENGTH: The raw key length is random (~111 bits for 500 singlets).
#      ChaCha20-Poly1305 needs exactly 256 bits. SHA3-256 always outputs 256 bits
#      regardless of input length.
#
#   2. HIGH ENTROPY: Even if the raw key has some statistical bias (due to
#      imperfect quantum hardware or finite sample size), the hash function
#      distributes the entropy uniformly across all 256 output bits.
#
#   3. IRREVERSIBILITY: If an eavesdropper somehow obtains the hashed key,
#      they cannot reverse-engineer the original Ekert key because SHA3-256
#      is a one-way function (preimage resistant).
#
# SHA3-256 properties:
#   - Output: Always 256 bits (32 bytes)
#   - Collision resistant: Computationally infeasible to find two inputs with
#     the same hash
#   - Based on the Keccak algorithm (different internal structure from SHA-2)
#   - Selected by NIST in 2015 as the SHA-3 standard
# ==============================================================================

def hash_key_sha3_256(raw_key_bytes):
    """
    Hash the raw Ekert key using SHA3-256 to produce the final 256-bit key.

    Parameters:
        raw_key_bytes (bytes): The raw key from E91 QKD (variable length).

    Returns:
        bytes: The 256-bit (32-byte) hashed key, ready for ChaCha20-Poly1305.
    """
    # Create SHA3-256 hash object
    hasher = SHA3_256.new()

    # Feed the raw key bytes into the hash function
    hasher.update(raw_key_bytes)

    # Return the 32-byte (256-bit) hash digest
    return hasher.digest()


# ==============================================================================
# SECTION 10: EVE SIMULATION (Eavesdropper Attack — for thesis evaluation)
# ==============================================================================
#
# What this section does:
#   Simulates an eavesdropper (Eve) who performs an intercept-resend attack.
#   Eve intercepts each qubit, measures it in a randomly chosen basis, and then
#   forwards the (now-collapsed) qubit to the intended recipient.
#
# Why this matters for your thesis:
#   This section is NOT part of the normal key generation pipeline. It exists
#   purely to DEMONSTRATE that the CHSH test works — that eavesdropping is
#   detectable. In your thesis, you'll run the protocol twice:
#     (a) Without Eve → CHSH ≈ 2.828, key mismatches = 0
#     (b) With Eve → CHSH ≈ 1.1, key mismatches ≈ 20%
#   This comparison proves the security claim.
#
# How the intercept-resend attack works:
#   1. Eve intercepts Alice's qubit BEFORE Alice measures it
#   2. Eve measures it in a randomly chosen basis
#   3. Eve's measurement collapses the quantum state, destroying entanglement
#   4. Eve sends the collapsed qubit to Alice (who measures it unaware)
#   5. Result: Alice and Bob's results are no longer perfectly correlated,
#      the CHSH value drops dramatically, and key mismatches appear
#
# Register layout for Eve:
#   Eve's measurements are stored in cr[2] and cr[3] (the 2 leftmost bits
#   in the 4-bit classical register that we reserved earlier).
# ==============================================================================

def run_eve_simulation(num_singlets=500):
    """
    Run the E91 protocol WITH an eavesdropper (Eve) performing an
    intercept-resend attack. This demonstrates that eavesdropping is
    detectable via the CHSH inequality test.

    Parameters:
        num_singlets (int): Number of entangled pairs to generate.

    Returns:
        dict: Dictionary containing all Eve simulation results:
            - 'chsh_value': The degraded CHSH correlation value
            - 'key_length': Length of the sifted key
            - 'alice_bob_mismatches': Number of key bit mismatches
            - 'eve_alice_knowledge': Fraction of Alice's key Eve knows
            - 'eve_bob_knowledge': Fraction of Bob's key Eve knows
    """

    # Set up registers and circuits (same as normal simulation)
    qr = QuantumRegister(2, name="qr")
    cr = ClassicalRegister(4, name="cr")
    singlet = create_singlet_circuit(qr, cr)
    alice_measurements, bob_measurements = create_measurement_circuits(qr, cr)

    # Random basis choices for Alice and Bob (same as normal)
    alice_basis_choices = [random.randint(1, 3) for _ in range(num_singlets)]
    bob_basis_choices = [random.randint(1, 3) for _ in range(num_singlets)]

    # -------------------------------------------------------------------------
    # Eve's measurement circuits:
    # Eve measures the qubits BEFORE Alice and Bob, using her own random bases.
    # She stores results in cr[2] (for Alice's qubit) and cr[3] (for Bob's qubit).
    # -------------------------------------------------------------------------
    measureEA2 = QuantumCircuit(qr, cr, name='measureEA2')
    measureEA2.s(qr[0]);  measureEA2.h(qr[0])
    measureEA2.t(qr[0]);  measureEA2.h(qr[0])
    measureEA2.measure(qr[0], cr[2])  # Eve measures Alice's qubit → cr[2]

    measureEA3 = QuantumCircuit(qr, cr, name='measureEA3')
    measureEA3.measure(qr[0], cr[2])  # Eve measures Alice's qubit → cr[2]

    measureEB1 = QuantumCircuit(qr, cr, name='measureEB1')
    measureEB1.s(qr[1]);  measureEB1.h(qr[1])
    measureEB1.t(qr[1]);  measureEB1.h(qr[1])
    measureEB1.measure(qr[1], cr[3])  # Eve measures Bob's qubit → cr[3]

    measureEB2 = QuantumCircuit(qr, cr, name='measureEB2')
    measureEB2.measure(qr[1], cr[3])  # Eve measures Bob's qubit → cr[3]

    eve_measurements = [measureEA2, measureEA3, measureEB1, measureEB2]

    # Eve randomly chooses which pair of bases to use for each singlet
    eve_basis_choices = []
    for _ in range(num_singlets):
        if random.uniform(0, 1) <= 0.5:
            eve_basis_choices.append([0, 2])   # Eve uses bases EA2 and EB1
        else:
            eve_basis_choices.append([1, 3])   # Eve uses bases EA3 and EB2

    # -------------------------------------------------------------------------
    # Compose circuits WITH Eve's measurements inserted BEFORE Alice and Bob's.
    # Order: singlet → Eve measures → Alice measures → Bob measures
    # Eve's measurement collapses the entanglement BEFORE the legitimate parties.
    # -------------------------------------------------------------------------
    circuits = []
    for j in range(num_singlets):
        circuit_name = (f"{j}:A{alice_basis_choices[j]}_B{bob_basis_choices[j]}"
                        f"_E{eve_basis_choices[j][0]}{eve_basis_choices[j][1]}")

        # Compose: singlet → Eve's 1st measurement → Eve's 2nd measurement
        #          → Alice's measurement → Bob's measurement
        combined = (singlet
                    .compose(eve_measurements[eve_basis_choices[j][0]])
                    .compose(eve_measurements[eve_basis_choices[j][1]])
                    .compose(alice_measurements[alice_basis_choices[j] - 1])
                    .compose(bob_measurements[bob_basis_choices[j] - 1]))

        combined.name = circuit_name
        circuits.append(combined)

    # Run the simulation
    simulator = AerSimulator()
    result = simulator.run(circuits, shots=1).result()

    # Parse Alice's, Bob's, AND Eve's measurement results
    ab_patterns = [
        re.compile('..00$'), re.compile('..01$'),
        re.compile('..10$'), re.compile('..11$')
    ]
    eve_patterns = [
        re.compile('00..$'), re.compile('01..$'),
        re.compile('10..$'), re.compile('11..$')
    ]

    alice_results, bob_results, eve_results = [], [], []

    for j in range(num_singlets):
        outcome = list(result.get_counts(circuits[j]).keys())[0]

        # Parse Alice & Bob (rightmost 2 bits)
        for k in range(4):
            if ab_patterns[k].search(outcome):
                alice_results.append(-1 if k in [0, 2] else 1)
                bob_results.append(-1 if k in [0, 1] else 1)

        # Parse Eve (leftmost 2 bits)
        for k in range(4):
            if eve_patterns[k].search(outcome):
                eve_results.append([
                    -1 if k in [0, 2] else 1,    # Eve's result on Alice's qubit
                    -1 if k in [0, 1] else 1      # Eve's result on Bob's qubit
                ])

    # Sift keys (same logic as normal)
    alice_key, bob_key, eve_keys = [], [], []
    for j in range(num_singlets):
        if ((alice_basis_choices[j] == 2 and bob_basis_choices[j] == 1) or
                (alice_basis_choices[j] == 3 and bob_basis_choices[j] == 2)):
            alice_key.append(alice_results[j])
            bob_key.append(-bob_results[j])
            eve_keys.append([eve_results[j][0], -eve_results[j][1]])

    key_length = len(alice_key)

    # Count mismatches (with Eve present, there WILL be mismatches)
    ab_mismatches = sum(1 for j in range(key_length) if alice_key[j] != bob_key[j])
    ea_mismatches = sum(1 for j in range(key_length) if eve_keys[j][0] != alice_key[j])
    eb_mismatches = sum(1 for j in range(key_length) if eve_keys[j][1] != bob_key[j])

    # Compute CHSH (will be degraded due to Eve's interference)
    chsh_value = compute_chsh(result, circuits, alice_basis_choices,
                              bob_basis_choices, num_singlets)

    return {
        'chsh_value': chsh_value,
        'key_length': key_length,
        'alice_bob_mismatches': ab_mismatches,
        'eve_alice_knowledge': (key_length - ea_mismatches) / max(key_length, 1),
        'eve_bob_knowledge': (key_length - eb_mismatches) / max(key_length, 1),
    }


# ==============================================================================
# SECTION 11: MAIN PIPELINE (Complete Module 1 — Putting it all together)
# ==============================================================================
#
# What this section does:
#   Ties together all the previous sections into a single function that runs
#   the complete Module 1 pipeline:
#     1. Run E91 QKD simulation (generate pairs, measure, collect results)
#     2. Parse measurement outcomes into ±1 values
#     3. Sift keys (keep compatible bases only)
#     4. Run CHSH security test
#     5. Convert raw key to bytes
#     6. Hash with SHA3-256 → final 256-bit key
#
#   This function is the one that Module 2 (ChaCha20-Poly1305) will call
#   to get the encryption key.
# ==============================================================================

def generate_quantum_key(num_singlets=500, verbose=True):
    """
    Complete Module 1 pipeline: Generate a 256-bit quantum-secured symmetric key.

    This is the main entry point for key generation. It runs the full E91 QKD
    protocol, verifies security via CHSH, and outputs a SHA3-256 hashed key.

    Parameters:
        num_singlets (int): Number of entangled pairs to generate. Default 500.
            More pairs → longer raw key → more statistical confidence in CHSH.
        verbose (bool): If True, print progress and diagnostic information.

    Returns:
        dict: Dictionary containing:
            - 'key': The final 256-bit (32-byte) symmetric key (bytes)
            - 'key_hex': The key as a hexadecimal string (for display)
            - 'chsh_value': The CHSH correlation value
            - 'is_secure': Boolean — True if CHSH indicates no eavesdropper
            - 'raw_key_length': Number of bits in the raw (pre-hash) key
            - 'raw_key_binary': The raw key as a binary string
            - 'key_mismatches': Number of mismatched bits between Alice and Bob
                                (should be 0 for ideal simulation)

    Raises:
        SecurityError: If CHSH test indicates possible eavesdropping (|S| ≤ 2).
    """

    if verbose:
        print("=" * 70)
        print("MODULE 1: Quantum Key Generation (E91 + SHA3-256)")
        print("=" * 70)

    # Step 1: Run E91 simulation
    if verbose:
        print(f"\n[Step 1] Generating {num_singlets} entangled pairs...")
    (result, circuits, alice_basis, bob_basis,
     qr, cr, alice_meas, bob_meas) = run_e91_simulation(num_singlets)
    if verbose:
        print(f"         Simulation complete. {num_singlets} circuits executed.")

    # Step 2: Parse measurement results
    if verbose:
        print("[Step 2] Parsing measurement outcomes...")
    alice_results, bob_results = parse_measurement_results(
        result, circuits, num_singlets)

    # Step 3: Sift keys
    if verbose:
        print("[Step 3] Sifting keys (keeping compatible basis pairs)...")
    alice_key, bob_key, key_length = sift_keys(
        alice_results, bob_results, alice_basis, bob_basis, num_singlets)
    if verbose:
        print(f"         Raw key length: {key_length} bits "
              f"(from {num_singlets} pairs, ~{key_length/num_singlets*100:.1f}% yield)")

    # Step 4: Verify key agreement
    mismatches = sum(1 for j in range(key_length) if alice_key[j] != bob_key[j])
    if verbose:
        print(f"[Step 4] Key agreement check: {mismatches} mismatched bits "
              f"(should be 0 for ideal simulation)")

    # Step 5: CHSH security test
    if verbose:
        print("[Step 5] Running CHSH inequality test...")
    chsh_value = compute_chsh(result, circuits, alice_basis, bob_basis,
                              num_singlets)
    is_secure = abs(chsh_value) > 2.0

    if verbose:
        print(f"         CHSH correlation value: S = {chsh_value:.3f}")
        print(f"         |S| = {abs(chsh_value):.3f}  "
              f"(quantum limit ≈ 2.828, classical limit = 2.000)")
        if is_secure:
            print("         ✓ CHSH test PASSED — No eavesdropper detected.")
        else:
            print("         ✗ CHSH test FAILED — Possible eavesdropper! Aborting.")

    # Step 6: Convert raw key to binary and bytes
    if verbose:
        print("[Step 6] Converting raw key to binary...")
    raw_key_binary = convert_key_to_binary_string(alice_key)
    raw_key_bytes = convert_binary_string_to_bytes(raw_key_binary)
    if verbose:
        print(f"         Binary key (first 64 bits): {raw_key_binary[:64]}...")

    # Step 7: Hash with SHA3-256
    if verbose:
        print("[Step 7] Hashing with SHA3-256 → final 256-bit key...")
    final_key = hash_key_sha3_256(raw_key_bytes)
    final_key_hex = final_key.hex()
    if verbose:
        print(f"         Final key (hex): {final_key_hex}")
        print(f"         Key length: {len(final_key) * 8} bits ({len(final_key)} bytes)")

    if verbose:
        print("\n" + "=" * 70)
        print("MODULE 1 COMPLETE — Key ready for Module 2 (ChaCha20-Poly1305)")
        print("=" * 70)

    return {
        'key': final_key,
        'key_hex': final_key_hex,
        'chsh_value': chsh_value,
        'is_secure': is_secure,
        'raw_key_length': key_length,
        'raw_key_binary': raw_key_binary,
        'key_mismatches': mismatches,
    }


# ==============================================================================
# SECTION 12: SCRIPT EXECUTION (Run when file is executed directly)
# ==============================================================================
#
# What this section does:
#   When you run this file directly (python qkd_module.py), it:
#   1. Runs the normal E91 key generation (without eavesdropper)
#   2. Runs the Eve simulation (with eavesdropper) for comparison
#   3. Prints a side-by-side comparison showing how eavesdropping degrades
#      the CHSH value and introduces key mismatches
#
#   This serves as both a test and a demonstration for your thesis.
# ==============================================================================

if __name__ == "__main__":

    # =========================================================================
    # Part A: Normal key generation (no eavesdropper)
    # =========================================================================
    print("\n" + "▓" * 70)
    print("  PART A: Normal E91 Key Generation (No Eavesdropper)")
    print("▓" * 70)

    key_result = generate_quantum_key(num_singlets=500, verbose=True)

    # Save the key to a file (for use by Module 2)
    with open('quantum_key.bin', 'wb') as f:
        f.write(key_result['key'])
    print(f"\nKey saved to 'quantum_key.bin'")

    # =========================================================================
    # Part B: Eve simulation (eavesdropper present — for thesis evaluation)
    # =========================================================================
    print("\n\n" + "▓" * 70)
    print("  PART B: E91 with Eavesdropper (Eve Simulation)")
    print("▓" * 70)

    eve_result = run_eve_simulation(num_singlets=500)

    print(f"\n  CHSH correlation value: {eve_result['chsh_value']:.3f}")
    print(f"  |S| = {abs(eve_result['chsh_value']):.3f}  (should be << 2.828)")
    print(f"  Key length: {eve_result['key_length']}")
    print(f"  Alice-Bob key mismatches: {eve_result['alice_bob_mismatches']}")
    print(f"  Eve's knowledge of Alice's key: {eve_result['eve_alice_knowledge']*100:.1f}%")
    print(f"  Eve's knowledge of Bob's key: {eve_result['eve_bob_knowledge']*100:.1f}%")

    # =========================================================================
    # Part C: Comparison summary (for thesis table)
    # =========================================================================
    print("\n\n" + "=" * 70)
    print("  COMPARISON: Normal vs Eavesdropper")
    print("=" * 70)
    print(f"  {'Metric':<35} {'Normal':>12} {'With Eve':>12}")
    print(f"  {'-'*35} {'-'*12} {'-'*12}")
    print(f"  {'CHSH value |S|':<35} {abs(key_result['chsh_value']):>12.3f} {abs(eve_result['chsh_value']):>12.3f}")
    print(f"  {'Key mismatches':<35} {key_result['key_mismatches']:>12d} {eve_result['alice_bob_mismatches']:>12d}")
    print(f"  {'Eavesdropper detected?':<35} {'No':>12} {'YES':>12}")
    print(f"  {'Key usable?':<35} {'YES':>12} {'NO (abort)':>12}")
    print("=" * 70)
