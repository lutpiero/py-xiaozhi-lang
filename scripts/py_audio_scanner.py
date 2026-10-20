#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import sounddevice as sd


def detect_audio_devices():
    """
    Detect and list all audio devices (using sounddevice)
    """
    print("\n===== 音频设备检测 (SoundDevice) =====\n")

    # Get default device
    default_input = sd.default.device[0] if sd.default.device else None
    default_output = sd.default.device[1] if sd.default.device else None

    # Store found devices
    input_devices = []
    output_devices = []

    # List all devices
    devices = sd.query_devices()
    for i, dev_info in enumerate(devices):
        # Print device information
        print(f"设备 {i}: {dev_info['name']}")
        print(f"  - 输入通道: {dev_info['max_input_channels']}")
        print(f"  - 输出通道: {dev_info['max_output_channels']}")
        print(f"  - 默认采样率: {dev_info['default_samplerate']}")

        # Mark default device
        if i == default_input:
            print("  - 🎤 系统默认输入设备")
        if i == default_output:
            print("  - 🔊 系统默认输出设备")

        # Identify input device (microphone)
        if dev_info["max_input_channels"] > 0:
            input_devices.append((i, dev_info["name"]))
            if "USB" in dev_info["name"]:
                print("  - 可能是USB麦克风 🎤")

        # identifies the output device (speaker)
        if dev_info["max_output_channels"] > 0:
            output_devices.append((i, dev_info["name"]))
            if "Headphones" in dev_info["name"]:
                print("  - 可能是耳机输出 🎧")
            elif "USB" in dev_info["name"] and dev_info["max_output_channels"] > 0:
                print("  - 可能是USB扬声器 🔊")

        print("")

    # Summarize found devices
    print("\n===== 设备总结 =====\n")

    print("找到的输入设备（麦克风）:")
    for idx, name in input_devices:
        default_mark = " (默认)" if idx == default_input else ""
        print(f"  - 设备 {idx}: {name}{default_mark}")

    print("\n找到的输出设备（扬声器）:")
    for idx, name in output_devices:
        default_mark = " (默认)" if idx == default_output else ""
        print(f"  - 设备 {idx}: {name}{default_mark}")

    # Recommended device
    print("\n推荐设备配置:")

    # Recommended microphone
    recommended_mic = None
    if default_input is not None:
        recommended_mic = (default_input, devices[default_input]["name"])
    elif input_devices:
        # Prioritize USB devices
        for idx, name in input_devices:
            if "USB" in name:
                recommended_mic = (idx, name)
                break
        if recommended_mic is None:
            recommended_mic = input_devices[0]

    # Recommended speakers
    recommended_speaker = None
    if default_output is not None:
        recommended_speaker = (default_output, devices[default_output]["name"])
    elif output_devices:
        # Prioritize headphones
        for idx, name in output_devices:
            if "Headphones" in name:
                recommended_speaker = (idx, name)
                break
        if recommended_speaker is None:
            recommended_speaker = output_devices[0]

    if recommended_mic:
        print(f"  - 麦克风: 设备 {recommended_mic[0]} ({recommended_mic[1]})")
    else:
        print("  - 未找到可用麦克风")

    if recommended_speaker:
        print(f"  - 扬声器: 设备 {recommended_speaker[0]} ({recommended_speaker[1]})")
    else:
        print("  - 未找到可用扬声器")

    print("\n===== SoundDevice配置示例 =====\n")

    if recommended_mic:
        print("# 麦克风初始化代码")
        print(f"input_device_id = {recommended_mic[0]}  # {recommended_mic[1]}")
        print("input_stream = sd.InputStream(")
        print("    samplerate=16000,")
        print("    channels=1,")
        print("    dtype=np.int16,")
        print("    blocksize=1024,")
        print(f"    device={recommended_mic[0]},")
        print("    callback=input_callback)")

    if recommended_speaker:
        print("\n# 扬声器初始化代码")
        print(
            f"output_device_id = {recommended_speaker[0]}  # "
            f"{recommended_speaker[1]}"
        )
        print("output_stream = sd.OutputStream(")
        print("    samplerate=44100,")
        print("    channels=1,")
        print("    dtype=np.int16,")
        print("    blocksize=1024,")
        print(f"    device={recommended_speaker[0]},")
        print("    callback=output_callback)")

    print("\n===== 设备测试 =====\n")

    # Test recommended device
    if recommended_mic:
        print(f"正在测试麦克风 (设备 {recommended_mic[0]})...")
        try:
            sd.rec(
                int(1 * 16000),
                samplerate=16000,
                channels=1,
                device=recommended_mic[0],
                dtype=np.int16,
            )
            sd.wait()
            print("✓ 麦克风测试成功")
        except Exception as e:
            print(f"✗ 麦克风测试失败: {e}")

    if recommended_speaker:
        print(f"正在测试扬声器 (设备 {recommended_speaker[0]})...")
        try:
            # Generate test audio (440Hz sine wave)
            duration = 0.5
            sample_rate = 44100
            t = np.linspace(0, duration, int(sample_rate * duration))
            test_audio = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)

            sd.play(test_audio, samplerate=sample_rate, device=recommended_speaker[0])
            sd.wait()
            print("✓ 扬声器测试成功")
        except Exception as e:
            print(f"✗ 扬声器测试失败: {e}")

    return recommended_mic, recommended_speaker


if __name__ == "__main__":
    try:
        mic, speaker = detect_audio_devices()
        print("\n检测完成！")
    except Exception as e:
        print(f"检测过程中出错: {e}")
