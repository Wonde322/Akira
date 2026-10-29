import sys
from types import SimpleNamespace


def test_core_idle_work_and_audio_have_separate_levels(qapp):
    from desktop_app.core import CoreWidget
    core = CoreWidget()
    for _ in range(40): core._advance()
    idle = core.energy
    core.set_working(True)
    for _ in range(40): core._advance()
    assert core.energy > idle * 10
    core.set_working(False)
    core.set_spectrum([0.9] * 32)
    for _ in range(40): core._advance()
    assert core.energy > 0.8
    assert len(core.frames)==256
    assert all(not frame.isNull() for frame in core.frames)
    core.resize(600, 240)
    core.show(); qapp.processEvents()
    assert core.timer.isActive()
    assert not core.grab().isNull()
    core.hide()
    assert not core.timer.isActive()


def test_audio_never_falls_back_to_microphone(monkeypatch, qapp):
    from desktop_app.core import SystemAudioSpectrum
    opened = []
    fake = SimpleNamespace(query_devices=lambda: [{'name': 'Built-in Microphone', 'max_input_channels': 1}],
                           InputStream=lambda **kwargs: opened.append(kwargs))
    monkeypatch.setitem(sys.modules, 'sounddevice', fake)
    monitor = SystemAudioSpectrum()
    monitor.run()
    assert opened == []


def test_loopback_audio_emits_real_fft_bands(monkeypatch, qapp):
    import numpy as np
    from desktop_app.core import SystemAudioSpectrum
    monitor = SystemAudioSpectrum()
    opened, spectra = [], []
    monitor.spectrum.connect(spectra.append)
    class Stream:
        def __init__(self, **kwargs):
            opened.append(kwargs['device'])
            data = np.sin(np.arange(2048) * 2 * np.pi * 440 / 48000).reshape(-1, 1).astype('float32') * 0.2
            kwargs['callback'](data, 2048, None, None)
        def __enter__(self): return self
        def __exit__(self, *args): pass
    fake = SimpleNamespace(query_devices=lambda: [
        {'name': 'Built-in Microphone', 'max_input_channels': 1, 'default_samplerate': 48000},
        {'name': 'BlackHole 2ch', 'max_input_channels': 2, 'default_samplerate': 48000}], InputStream=Stream)
    monkeypatch.setitem(sys.modules, 'sounddevice', fake)
    monkeypatch.setattr(monitor, 'isInterruptionRequested', lambda: True)
    monitor.run()
    assert opened == [1]
    assert len(spectra[0]) == 32
    assert max(spectra[0]) > 0.2


def test_idle_animation_keeps_advancing(qapp, monkeypatch):
    from desktop_app.core import CoreWidget
    core=CoreWidget()
    clock=[core.last_tick]
    monkeypatch.setattr('desktop_app.core.time.monotonic', lambda: clock[0])
    start=core.phase
    for _ in range(10):
        clock[0]+=.05
        core._advance()
    assert core.phase>start
    assert core.bank==0
    assert core.frames[0].toImage()!=core.frames[16].toImage()


def test_core_wrap_is_continuous_and_faster(qapp, monkeypatch):
    from desktop_app.core import CoreWidget
    core = CoreWidget()
    core.resize(320, 210)
    core.energy = .025
    core.phase = 255.999
    before = core.grab().toImage()
    core.phase = .001
    after = core.grab().toImage()
    # Rendering across the wrap must approach the same frame from both sides.
    import numpy as np
    a = np.frombuffer(before.bits(), dtype=np.uint8).astype(float)
    b = np.frombuffer(after.bits(), dtype=np.uint8).astype(float)
    assert np.abs(a-b).mean() < 1
    core.phase = 255
    now = core.last_tick + .05
    monkeypatch.setattr('desktop_app.core.time.monotonic', lambda: now)
    core._advance()
    assert 0 < core.phase < 4
    assert core.timer.interval() == 16


def test_prepared_cycle_has_no_outlier_at_loop_seam(qapp):
    import numpy as np
    from PySide6.QtGui import QImage
    from desktop_app.core import CoreWidget
    core = CoreWidget()
    def pixels(index):
        image = core.frames[index].toImage().convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        return np.frombuffer(image.bits(), dtype=np.uint8).astype(np.int16)
    first = previous = pixels(0)
    differences = []
    for index in range(1, len(core.frames)):
        current = pixels(index)
        differences.append(np.abs(current-previous).mean())
        previous = current
    seam = np.abs(first-previous).mean()
    assert np.median(differences) > 0
    assert seam < 2 * np.median(differences)


def test_cycle_does_not_switch_plasma_colour_between_poses(qapp):
    import numpy as np
    from PySide6.QtGui import QImage
    from desktop_app.core import CoreWidget
    core = CoreWidget()
    colours = []
    for frame in core.frames:
        image = frame.toImage().convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        rgba = np.frombuffer(image.bits(), dtype=np.uint8).reshape(-1, 4).astype(float)
        colours.append(rgba[:, :3].sum(axis=0)/max(1, rgba[:, 3].sum()))
    # A changing pose must not turn the entire coloured ring pale/white.
    assert np.ptp(colours, axis=0).max() < .02


def test_timer_stall_does_not_skip_a_large_part_of_the_cycle(qapp, monkeypatch):
    from desktop_app.core import CoreWidget
    core = CoreWidget()
    core.energy = 1
    core.set_working(True)
    monkeypatch.setattr('desktop_app.core.time.monotonic', lambda: core.last_tick + 2)
    core._advance()
    assert 0 < core.phase <= 168/30
