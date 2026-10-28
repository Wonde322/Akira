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
    assert len(core.frames) == 128
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
