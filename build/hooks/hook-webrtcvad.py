# -*- mode: python ; coding: utf-8 -*-
"""Hook override: корректное имя dist-info для webrtcvad_wheels.

pyinstaller-hooks-contrib ищет 'webrtcvad' dist-info, но пакет
устанавливается как 'webrtcvad_wheels-2.0.14.dist-info'.
"""

from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad_wheels")