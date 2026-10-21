"""Bloom: a VA machine built around a modulator that bends time.

The reference model (`docs/bloom-machine.md`, milestone B0): what the DSP code
must compute, as pure Python. Nothing here touches a firmware image.

    clock    the frame's song position and tempo, as beats and seconds
    pulse    PULSE: the glide, its modes (smooth, land, step), shapes and TILT
    osc      the PolyBLEP oscillators
    duck     DUCK, the built-in sidechain envelope
    sound    a Bloom sound: its controls, in their own units
    presets  the factory sounds, which double as acceptance targets
    voice    one voice rendered: oscillators, PULSE on the cutoff and the chop
"""
